# -*- coding: utf-8 -*-
import json
import logging
from collections import defaultdict
from functools import wraps
from logging.config import dictConfig
from subprocess import call

import redis
import requests
from flask import Flask, Response, redirect, render_template, request, session, url_for
from flask_migrate import Migrate
from pylti.flask import lti
from redis.exceptions import ConnectionError
from rq import Queue, get_current_job
from rq.exceptions import NoSuchJobError
from rq.job import Job
from sqlalchemy.sql import text

import config
from models import Course, Extension, Quiz, User, db
from utils import (
    extend_quiz,
    get_course,
    get_or_create,
    get_quizzes,
    get_user,
    missing_and_stale_quizzes,
    search_students,
    update_job,
)

conn = redis.from_url(config.REDIS_URL)
q = Queue("quizext", connection=conn)

app = Flask(__name__)

app.config.from_object("config")

dictConfig(config.LOGGING_CONFIG)
logger = logging.getLogger("app")

db.init_app(app)
migrate = Migrate(app, db)

json_headers = {
    "Authorization": "Bearer " + config.API_KEY,
    "Content-type": "application/json",
}


def check_valid_user(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        """
        Decorator to check if the user is allowed access to the app.
        If user is allowed, return the decorated function.
        Otherwise, return an error page with corresponding message.
        """
        canvas_user_id = session.get("canvas_user_id")
        lti_logged_in = session.get("lti_logged_in", False)
        if not lti_logged_in or not canvas_user_id:
            return render_template("error.html", message="Not allowed!")
        if "course_id" not in kwargs.keys():
            return render_template("error.html", message="No course_id provided.")
        course_id = int(kwargs.get("course_id"))

        if not session.get("is_admin", False):
            enrollments_url = "{}courses/{}/enrollments".format(
                config.API_URL, course_id
            )

            payload = {
                "user_id": canvas_user_id,
                "type": ["TeacherEnrollment", "TaEnrollment", "DesignerEnrollment"],
            }

            user_enrollments_response = requests.get(
                enrollments_url, data=json.dumps(payload), headers=json_headers
            )
            user_enrollments = user_enrollments_response.json()

            if not user_enrollments or "errors" in user_enrollments:
                message = (
                    "You are not enrolled in this course as a Teacher, "
                    "TA, or Designer."
                )
                return render_template("error.html", message=message)

        return f(*args, **kwargs)

    return decorated_function


def error(exception=None):
    return Response(
        render_template(
            "error.html",
            message=exception.get(
                "exception", "Please contact your System Administrator."
            ),
        )
    )


@app.context_processor
def add_google_analytics_id():
    return dict(GOOGLE_ANALYTICS=config.GOOGLE_ANALYTICS)


@app.route("/", methods=["POST", "GET"])
def index():
    """
    Default app index.
    """
    return "Please contact your System Administrator."


@app.route("/status", methods=["GET"])
def status():  # pragma: no cover
    """
    Runs smoke tests and reports status
    """
    try:
        job_queue_length = len(q.jobs)
    except ConnectionError:
        job_queue_length = -1

    status = {
        "tool": "Quiz Extensions",
        "checks": {
            "index": False,
            "xml": False,
            "api_key": False,
            "redis": False,
            "db": False,
            "worker": False,
        },
        "url": url_for("index", _external=True),
        "api_url": config.API_URL,
        "debug": app.debug,
        "xml_url": url_for("xml", _external=True),
        "job_queue": job_queue_length,
    }

    # Check index
    try:
        response = requests.get(url_for("index", _external=True), verify=False)
        status["checks"]["index"] = (
            response.text == "Please contact your System Administrator."
        )
    except Exception:
        logger.exception("Index check failed.")

    # Check xml
    try:
        response = requests.get(url_for("xml", _external=True), verify=False)
        status["checks"]["xml"] = "application/xml" in response.headers.get(
            "Content-Type"
        )
    except Exception:
        logger.exception("XML check failed.")

    # Check API Key
    try:
        response = requests.get(
            "{}users/self".format(config.API_URL),
            headers={"Authorization": "Bearer " + config.API_KEY},
        )
        status["checks"]["api_key"] = response.status_code == 200
    except Exception:
        logger.exception("API Key check failed.")

    # Check redis
    try:
        response = conn.echo("test")
        status["checks"]["redis"] = response == b"test"
    except ConnectionError:
        logger.exception("Redis connection failed.")

    # Check DB connection
    try:
        db.session.query(text("1")).all()
        status["checks"]["db"] = True
    except Exception:
        logger.exception("DB connection failed.")

    # Check RQ Worker
    status["checks"]["worker"] = (
        call('ps aux | grep "rq worker" | grep "quizext" | grep -v grep', shell=True)
        == 0
    )

    # Overall health check - if all checks are True
    status["healthy"] = all(v is True for k, v in status["checks"].items())

    return Response(json.dumps(status), mimetype="application/json")


@app.route("/lti.xml", methods=["GET"])
def xml():
    """
    Returns the lti.xml file for the app.
    """
    from urllib.parse import urlparse

    domain = urlparse(request.url_root).netloc

    return Response(
        render_template("lti.xml", tool_id=config.LTI_TOOL_ID, domain=domain),
        mimetype="application/xml",
    )


@app.route("/quiz/<course_id>/", methods=["GET"])
@check_valid_user
@lti(error=error, request="session", role="staff", app=app)
def quiz(lti=lti, course_id=None):
    """
    Main landing page for the app.

    Displays a page to the user that allows them to select students
    to moderate quizzes for.
    """
    return render_template(
        "userselect.html", course_id=course_id, current_page_number=1
    )


@app.route("/refresh/<course_id>/", methods=["POST"])
def refresh(course_id=None):
    """
    Creates a new `refresh_background` job.

    :param course_id: The Canvas ID of the Course.
    :type course_id: int
    :rtype: flask.Response
    :returns: A JSON-formatted response containing a url for the started job.
    """
    job = q.enqueue_call(func=refresh_background, args=(course_id,))
    return Response(
        json.dumps({"refresh_job_url": url_for("job_status", job_key=job.get_id())}),
        mimetype="application/json",
        status=202,
    )


@app.route("/update/<course_id>/", methods=["POST"])
@check_valid_user
@lti(error=error, request="session", role="staff", app=app)
def update(lti=lti, course_id=None):
    """
    Creates a new `update_background` job.

    :param course_id: The Canvas ID of the Course.
    :type coruse_id: int
    :rtype: flask.Response
    :returns: A JSON-formatted response containing urls for the started jobs.
    """
    refresh_job = q.enqueue_call(func=refresh_background, args=(course_id,))
    update_job = q.enqueue_call(
        func=update_background,
        args=(course_id, request.get_json()),
        depends_on=refresh_job,
    )
    return Response(
        json.dumps(
            {
                "refresh_job_url": url_for("job_status", job_key=refresh_job.get_id()),
                "update_job_url": url_for("job_status", job_key=update_job.get_id()),
            }
        ),
        mimetype="application/json",
        status=202,
    )


@app.route("/jobs/<job_key>/", methods=["GET"])
def job_status(job_key):
    try:
        job = Job.fetch(job_key, connection=conn)
    except NoSuchJobError:
        return Response(
            json.dumps(
                {
                    "error": True,
                    "status_msg": "{} is not a valid job key.".format(job_key),
                }
            ),
            mimetype="application/json",
            status=404,
        )

    if job.is_finished:
        return Response(json.dumps(job.result), mimetype="application/json", status=200)
    elif job.is_failed:
        logger.error("Job {} failed.\n{}".format(job_key, job.exc_info))
        return Response(
            json.dumps(
                {
                    "error": True,
                    "status_msg": "Job {} failed to complete.".format(job_key),
                }
            ),
            mimetype="application/json",
            status=500,
        )
    else:
        return Response(json.dumps(job.meta), mimetype="application/json", status=202)


def update_background(course_id, extension_dict):
    """
    Update time on selected students' quizzes to a specified percentage.

    :param course_id: The Canvas ID of the Course to update in
    :type course_id: int
    :param extension_dict: A dictionary that includes the percent of
        time and a list of canvas user ids.

        Example:
        {
            'percent': '300',
            'user_ids': [
                '0123456',
                '1234567',
                '9867543',
                '5555555'
            ]
        }
    :type extension_dict: dict
    """
    job = get_current_job()

    update_job(job, 0, "Starting...", "started")

    with app.app_context():
        if not extension_dict:
            update_job(job, 0, "Invalid Request", "failed", error=True)
            logger.warning("Invalid Request: {}".format(extension_dict))
            return job.meta

        try:
            course_json = get_course(course_id)
        except requests.exceptions.HTTPError:
            update_job(job, 0, "Course not found.", "failed", error=True)
            logger.exception("Unable to find course #{}".format(course_id))
            return job.meta

        course_name = course_json.get("name", "<UNNAMED COURSE>")

        user_ids = extension_dict.get("user_ids", [])
        percent = extension_dict.get("percent", None)

        if not percent:
            update_job(job, 0, "`percent` field required.", "failed", error=True)
            logger.warning(
                "Percent field not provided. Request: {}".format(extension_dict)
            )
            return job.meta

        course, created = get_or_create(db.session, Course, canvas_id=course_id)
        course.course_name = course_name
        db.session.commit()

        for user_id in user_ids:
            try:
                canvas_user = get_user(course_id, user_id)

                sortable_name = canvas_user.get("sortable_name", "<MISSING NAME>")
                sis_id = canvas_user.get("sis_user_id")

            except requests.exceptions.HTTPError:
                # Unable to find user. Log and skip them.
                logger.warning(
                    "Unable to find user #{} in course #{}".format(user_id, course_id)
                )
                continue

            user, created = get_or_create(db.session, User, canvas_id=user_id)

            user.sortable_name = sortable_name
            user.sis_id = sis_id

            db.session.commit()

            # create/update extension
            extension, created = get_or_create(
                db.session, Extension, course_id=course.id, user_id=user.id
            )
            extension.percent = percent

            db.session.commit()

        quizzes = get_quizzes(course_id)
        num_quizzes = len(quizzes)
        quiz_time_list = []
        unchanged_quiz_time_list = []

        if num_quizzes < 1:
            update_job(
                job,
                0,
                "Sorry, there are no quizzes for this course.",
                "failed",
                error=True,
            )
            logger.warning(
                "No quizzes found for course {}. Unable to update.".format(course_id)
            )
            return job.meta

        for index, quiz in enumerate(quizzes):
            quiz_id = quiz.get("id", None)
            quiz_title = quiz.get("title", "[UNTITLED QUIZ]")

            comp_perc = int(((float(index)) / float(num_quizzes)) * 100)
            updating_str = "Updating quiz #{} - {} [{} of {}]"
            update_job(
                job,
                comp_perc,
                updating_str.format(quiz_id, quiz_title, index + 1, num_quizzes),
                "processing",
                error=False,
            )

            extension_response = extend_quiz(course_id, quiz, percent, user_ids)

            if extension_response.get("success", False) is True:
                # add/update quiz
                quiz_obj, created = get_or_create(
                    db.session, Quiz, canvas_id=quiz_id, course_id=course.id
                )
                quiz_obj.title = quiz_title
                quiz_obj.time_limit = quiz.get("time_limit")

                db.session.commit()

                added_time = extension_response.get("added_time", None)
                if added_time is not None:
                    quiz_time_list.append(
                        {"title": quiz_title, "added_time": added_time}
                    )
                else:
                    unchanged_quiz_time_list.append({"title": quiz_title})
            else:
                update_job(
                    job,
                    comp_perc,
                    extension_response.get("message", "An unknown error occured."),
                    "failed",
                    error=True,
                )
                logger.error("Extension failed: {}".format(extension_response))
                return job.meta

        msg_str = (
            "Success! {} {} been updated for {} student(s) to have {}% time. "
            "{} {} no time limit and were left unchanged."
        )

        message = msg_str.format(
            len(quiz_time_list),
            "quizzes have" if len(quiz_time_list) != 1 else "quiz has",
            len(user_ids),
            percent,
            len(unchanged_quiz_time_list),
            "quizzes have" if len(unchanged_quiz_time_list) != 1 else "quiz has",
        )

        update_job(job, 100, message, "complete", error=False)
        job.meta["quiz_list"] = quiz_time_list
        job.meta["unchanged_list"] = unchanged_quiz_time_list
        job.save()

        return job.meta


def refresh_background(course_id):
    """
    Look up existing extensions and apply them to new quizzes.

    :param course_id: The Canvas ID of the Course.
    :type course_id: int
    :rtype: dict
    :returns: A dictionary containing two parts:

        - success `bool` False if there was an error, True otherwise.
        - message `str` A long description of success or failure.
    """
    job = get_current_job()

    update_job(job, 0, "Starting...", "started")

    with app.app_context():
        course, created = get_or_create(db.session, Course, canvas_id=course_id)

        try:
            course_name = get_course(course_id).get("name", "<UNNAMED COURSE>")
            course.course_name = course_name
            db.session.commit()
        except requests.exceptions.HTTPError:
            update_job(job, 0, "Course not found.", "failed", error=True)
            logger.exception("Unable to find course #{}".format(course_id))

            return job.meta

        quizzes = missing_and_stale_quizzes(course_id)

        num_quizzes = len(quizzes)

        if num_quizzes < 1:
            update_job(
                job,
                100,
                "Complete. No quizzes required updates.",
                "complete",
                error=False,
            )

            return job.meta

        percent_user_map = defaultdict(list)

        inactive_list = []

        update_job(job, 0, "Getting past extensions.", "processing", False)
        for extension in course.extensions:
            # If extension is inactive, ignore.
            if not extension.active:
                inactive_list.append(extension.user.sortable_name)
                logger.debug("Extension #{} is inactive.".format(extension.id))
                continue

            user_canvas_id = (
                User.query.filter_by(id=extension.user_id).first().canvas_id
            )

            # Check if user is in course. If not, deactivate extension.
            try:
                canvas_user = get_user(course_id, user_canvas_id)

                # Skip user if not a student. Fixes an edge case where a
                # student that previously recieved an extension changes roles.
                enrolls = canvas_user.get("enrollments", [])
                type_list = [
                    e["type"]
                    for e in enrolls
                    if e["enrollment_state"] in ("active", "invited")
                ]
                if not any(t == "StudentEnrollment" for t in type_list):
                    logger.info(
                        (
                            "User #{} was found in course #{}, but is not an "
                            "active student. Deactivating extension #{}. Roles "
                            "found: {}"
                        ).format(
                            user_canvas_id,
                            course_id,
                            extension.id,
                            ", ".join(type_list) if len(enrolls) > 0 else None,
                        )
                    )
                    extension.active = False
                    db.session.commit()
                    inactive_list.append(extension.user.sortable_name)
                    continue

            except requests.exceptions.HTTPError:
                log_str = "User #{} not in course #{}. Deactivating extension #{}."
                logger.info(log_str.format(user_canvas_id, course_id, extension.id))
                extension.active = False
                db.session.commit()
                inactive_list.append(extension.user.sortable_name)
                continue

            percent_user_map[extension.percent].append(user_canvas_id)

        if len(percent_user_map) < 1:
            msg_str = "No active extensions were found.<br>"

            if len(inactive_list) > 0:
                msg_str += " Extensions for the following students are inactive:<br>{}"
                msg_str = msg_str.format("<br>".join(inactive_list))

            update_job(job, 100, msg_str, "complete", error=False)
            return job.meta

        for index, quiz in enumerate(quizzes):
            quiz_id = quiz.get("id", None)
            quiz_title = quiz.get("title", "[UNTITLED QUIZ]")

            comp_perc = int(((float(index)) / float(num_quizzes)) * 100)
            refreshing_str = "Refreshing quiz #{} - {} [{} of {}]"
            update_job(
                job,
                comp_perc,
                refreshing_str.format(quiz_id, quiz_title, index + 1, num_quizzes),
                "processing",
                error=False,
            )

            for percent, user_list in percent_user_map.items():
                extension_response = extend_quiz(course_id, quiz, percent, user_list)

                if extension_response.get("success", False) is True:
                    # add/update quiz
                    quiz_obj, created = get_or_create(
                        db.session, Quiz, canvas_id=quiz_id, course_id=course.id
                    )
                    quiz_obj.title = quiz_title
                    quiz_obj.time_limit = quiz.get("time_limit")

                    db.session.commit()
                else:
                    error_message = "Some quizzes couldn't be updated. "
                    error_message += extension_response.get("message", "")
                    update_job(job, comp_perc, error_message, "failed", error=True)
                    return job.meta

        msg = "{} quizzes have been updated.".format(len(quizzes))
        update_job(job, 100, msg, "complete", error=False)
        return job.meta


@app.route("/missing_and_stale_quizzes/<course_id>/", methods=["GET"])
def missing_and_stale_quizzes_check(course_id):
    """
    Check if there are missing quizzes.

    :param course_id: The Canvas ID of the Course.
    :type course_id: int
    :rtype: str
    :returns: A JSON-formatted string representation of a boolean.
        "true" if there are missing quizzes, "false" if there are not.
    """
    course = Course.query.filter_by(canvas_id=course_id).first()
    if course is None:
        # No record of this course. No need to update yet.
        return "false"

    num_extensions = Extension.query.filter_by(course_id=course.id).count()
    if num_extensions == 0:
        # There are no extensions for this course yet. No need to update.
        return "false"

    missing = len(missing_and_stale_quizzes(course_id, True)) > 0
    return json.dumps(missing)


@app.route("/filter/<course_id>/", methods=["GET"])
@check_valid_user
@lti(error=error, request="session", role="staff", app=app)
def filter(lti=lti, course_id=None):
    """
    Display a filtered and paginated list of students in the course.

    :param course_id:
    :type: int
    :rtype: str
    :returns: A list of students in the course using the template
        user_list.html.
    """

    query = request.args.get("query", "").lower()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", config.DEFAULT_PER_PAGE))

    user_list, max_pages = search_students(
        course_id, per_page=per_page, page=page, search_term=query
    )

    if not user_list or max_pages < 1:
        user_list = []
        max_pages = 1

    return render_template(
        "user_list.html", users=user_list, current_page_number=page, max_pages=max_pages
    )


@app.route("/launch", methods=["POST"])
@lti(error=error, request="initial", role="staff", app=app)
def lti_tool(lti=lti):
    """
    Bootstrapper for lti.
    """
    course_id = request.values.get("custom_canvas_course_id")
    canvas_user_id = request.values.get("custom_canvas_user_id")
    canvas_domain = request.values.get("custom_canvas_api_domain")

    if canvas_domain not in config.ALLOWED_CANVAS_DOMAINS:
        msg = (
            "<p>This tool is only available from the following domain(s):<br/>{}</p>"
            "<p>You attempted to access from this domain:<br/>{}</p>"
        )
        return render_template(
            "error.html",
            message=msg.format(", ".join(config.ALLOWED_CANVAS_DOMAINS), canvas_domain),
        )

    roles = request.values.get("roles", [])

    session["is_admin"] = "Administrator" in roles
    session["canvas_user_id"] = canvas_user_id
    session["lti_logged_in"] = True

    return redirect(url_for("quiz", course_id=course_id))
