# -*- coding: utf-8 -*-
import functools
import json
import logging
from collections import defaultdict
from logging.config import dictConfig
from subprocess import call
from urllib.parse import urlparse

import redis
import requests
from canvasapi import Canvas
from canvasapi.exceptions import CanvasException, ResourceDoesNotExist
from canvasapi.new_quiz import NewQuiz
from flask import (
    Flask,
    Response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_caching import Cache
from flask_migrate import Migrate
from pylti1p3.contrib.flask import (
    FlaskCacheDataStorage,
    FlaskMessageLaunch,
    FlaskOIDCLogin,
    FlaskRequest,
)
from pylti1p3.tool_config import ToolConfDict
from redis.exceptions import ConnectionError
from rq import Queue, get_current_job
from rq.exceptions import NoSuchJobError
from rq.job import Job
from sqlalchemy.sql import text

import config
from cli import register_cli
from models import (
    Course,
    Extension,
    Quiz,
    Registration,
    User,
    db,
)
from utils import (
    extend_quiz,
    get_or_create,
    missing_and_stale_quizzes,
    update_job,
)


class ReverseProxied(object):
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        scheme = environ.get("HTTP_X_FORWARDED_PROTO")
        # gunicorn 22.0.0 disallows underscores in headers, so we need to
        # use X-Script-Name to pass the SCRIPT_NAME and set with the app
        script_name = environ.get("HTTP_X_SCRIPT_NAME", "")
        if script_name:
            environ["SCRIPT_NAME"] = script_name
            path_info = environ["PATH_INFO"]
            if path_info.startswith(script_name):
                environ["PATH_INFO"] = path_info[len(script_name) :]

        if scheme:
            environ["wsgi.url_scheme"] = scheme
        return self.app(environ, start_response)


conn = redis.from_url(config.REDIS_URL)
q = Queue("quizext", connection=conn)

app = Flask(__name__)

app.config.from_object("config")
app.wsgi_app = ReverseProxied(app.wsgi_app)
dictConfig(config.LOGGING_CONFIG)
logger = logging.getLogger("app")
cache = Cache(app)
db.init_app(app)

migrate = Migrate(app, db)
register_cli(app)

# CanvasAPI requires /api/v1/ to be removed
canvas = Canvas(config.API_URL, config.API_KEY)

################################
# START LTI 1.3 IMPLEMENTATION #
################################


def get_lti_config():
    registrations = Registration.query.all()

    from collections import defaultdict

    settings = defaultdict(list)
    for registration in registrations:
        settings[registration.issuer].append(
            {
                "client_id": registration.client_id,
                "auth_login_url": registration.platform_login_auth_endpoint,
                "auth_token_url": registration.platform_service_auth_endpoint,
                "auth_audience": "null",  # TODO: figure out what this is for?
                "key_set_url": registration.platform_jwks_endpoint,
                "key_set": None,
                "deployment_ids": [d.deployment_id for d in registration.deployments],
            }
        )

    # TODO: figure out more elegant way to set public/private keys without double loop
    tool_conf = ToolConfDict(settings)
    for registration in registrations:
        # Currently pylti1.3 only allows one key per client id. For now just set first one.
        key = registration.key_set.keys[0]
        tool_conf.set_private_key(
            registration.issuer,
            # ensure type is string not bytes (varies based on DB type)
            (
                key.private_key
                if isinstance(key.private_key, str)
                else key.private_key.decode("utf-8")
            ),
            client_id=registration.client_id,
        )
        tool_conf.set_public_key(
            registration.issuer,
            # ensure type is string not bytes (varies based on DB type)
            (
                key.public_key
                if isinstance(key.public_key, str)
                else key.public_key.decode("utf-8")
            ),
            client_id=registration.client_id,
        )
    return tool_conf


# LTI 1.3
def lti_required(role=None):
    """
    LTI Protector - only allow access to routes if user has been authenticated and has a launch ID.
    You can also pass in a role to restrict access to certain roles
    e.g. @lti_required(role="staff")

    Args:
        role (str, optional): The role to restrict access to. Defaults to None.

    Returns:
        function: The decorated function.
    """
    # TODO: allow multiple roles simultaneously (e.g. ["staff", "student"])
    # TODO: Make these roles configurable via settings, with some defaults
    role_config = {
        "admin": [
            "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Administrator",
            "http://purl.imsglobal.org/vocab/lis/v2/membership#Administrator",
        ],
        "staff": [
            "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Administrator",
            "http://purl.imsglobal.org/vocab/lis/v2/membership#Administrator",
            "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor",
        ],
        "student": ["http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"],
    }

    def decorator(func):
        @functools.wraps(func)
        def secure_function(*args, **kwargs):
            # Ensure the requested role is in the role configuration.
            # This is mostly for if we publish this code elsewhere.
            if role not in role_config:
                app.logger.error(f"Invalid role: {role}")
                return (
                    "<h2>Unauthorized</h2>"
                    "<p>Invalid role configuration. Please contact support.</p>",
                    401,
                )

            if "launch_id" not in session:
                return (
                    # TODO: improve this message to be more user-friendly
                    "<h2>Unauthorized</h2>"
                    "<p>You must use this tool in an LTI context.</p>",
                    401,
                )

            if "roles" not in session:
                return (
                    "<h2>Unauthorized</h2><p>No roles found.</p>",
                    401,
                )

            if not any(
                role_vocab in session["roles"] for role_vocab in role_config[role]
            ):
                return (
                    "<h2>Unauthorized</h2>"
                    f"<p>You must be have the {role} role to use this tool.</p>",
                    401,
                )

            return func(*args, **kwargs)

        return secure_function

    return decorator


# LTI 1.3
class ExtendedFlaskMessageLaunch(FlaskMessageLaunch):
    def validate_nonce(self):
        """
        Used to bypass nonce validation for canvas.

        """
        iss = self.get_iss()
        if (
            iss == "https://canvas.instructure.com"
            or iss == "https://canvas.test.instructure.com"
            or iss == "https://canvas.beta.instructure.com"
        ):
            return self
        return super().validate_nonce()


def get_launch_data_storage():
    return FlaskCacheDataStorage(cache)


def init_views(app):
    # OIDC Login
    @app.route("/login/", methods=["GET", "POST"])
    def login():
        tool_conf = get_lti_config()
        launch_data_storage = get_launch_data_storage()
        flask_request = FlaskRequest()
        target_link_uri = flask_request.get_param("target_link_uri")

        if not target_link_uri:
            raise Exception('Missing "target_link_uri" param')

        oidc_login = FlaskOIDCLogin(
            flask_request, tool_conf, launch_data_storage=launch_data_storage
        )

        return oidc_login.enable_check_cookies(
            main_msg="Your browser prohibits saving cookies in an iframe.",
            click_msg="Click here to open the application in a new tab.",
        ).redirect(target_link_uri)

    @app.route("/launch/", methods=["POST"])
    def launch():
        tool_conf = get_lti_config()

        flask_request = FlaskRequest()
        launch_data_storage = get_launch_data_storage()
        message_launch = ExtendedFlaskMessageLaunch(
            flask_request, tool_conf, launch_data_storage=launch_data_storage
        )

        session["canvas_email"] = message_launch.get_launch_data().get("email")
        session["error"] = False
        session["roles"] = message_launch.get_launch_data().get(
            "https://purl.imsglobal.org/spec/lti/claim/roles"
        )
        session["launch_id"] = message_launch.get_launch_id()
        session["course_id"] = message_launch.get_launch_data()[
            "https://purl.imsglobal.org/spec/lti/claim/custom"
        ]["canvas_course_id"]
        session["canvas_user_id"] = message_launch.get_launch_data()[
            "https://purl.imsglobal.org/spec/lti/claim/custom"
        ]["canvas_user_id"]

        # Redirect to the quiz for your course
        return redirect(url_for("quiz", course_id=session["course_id"]))

    @app.route("/lticonfig/", methods=["GET"])
    def get_config():
        domain = urlparse(request.url_root).netloc
        return Response(
            render_template(
                "lti.json",
                domain=domain,
                url_scheme=app.config["PREFERRED_URL_SCHEME"],
            ),
            mimetype="application/json",
        )

    @app.route("/jwks/", methods=["GET"])
    def get_jwks():
        return get_lti_config().get_jwks()

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
    def utility_processor():
        def google_analytics():
            return app.config["GOOGLE_ANALYTICS"]

        return dict(google_analytics=google_analytics())

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
                # "lticonfig": False,
                "api_key": False,
                "redis": False,
                "db": False,
                "worker": False,
            },
            "url": url_for("index", _external=True),
            "api_url": config.API_URL,
            "debug": app.debug,
            # "config_url": url_for("lticonfig", _external=True),
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

        """
        # Check LTI Config
        try:
            response = requests.get(url_for("lticonfig", _external=True), verify=False)
            status["checks"]["lticonfig"] = "application/json" in response.headers.get(
                "Content-Type"
            )
        except Exception:
            logger.exception("LTI Config check failed.")
        """

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
            db.session.execute(text("SELECT 1"))
            status["checks"]["db"] = True
        except Exception:
            logger.exception("DB connection failed.")

        # Check RQ Worker
        status["checks"]["worker"] = (
            call(
                'ps aux | grep "rq worker" | grep "quizext" | grep -v grep', shell=True
            )
            == 0
        )

        # Overall health check - if all checks are True
        status["healthy"] = all(v is True for k, v in status["checks"].items())

        return Response(json.dumps(status), mimetype="application/json")

    @app.route("/quiz/<course_id>/", methods=["GET"])
    @lti_required(role="staff")
    def quiz(course_id=None):
        """
        Main landing page for the app.

        Displays a page to the user that allows them to select students
        to moderate quizzes for.
        """
        return render_template("userselect.html", course_id=course_id)

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
            json.dumps({"refresh_job_url": url_for("job_status", job_key=job.id)}),
            mimetype="application/json",
            status=202,
        )

    @app.route("/update/<course_id>/", methods=["POST"])
    @lti_required(role="staff")
    def update(course_id=None):
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
                    "refresh_job_url": url_for("job_status", job_key=refresh_job.id),
                    "update_job_url": url_for("job_status", job_key=update_job.id),
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
            return Response(
                json.dumps(job.result), mimetype="application/json", status=200
            )
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
            return Response(
                json.dumps(job.meta), mimetype="application/json", status=202
            )

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

        missing = len(missing_and_stale_quizzes(canvas, course_id, True)) > 0
        return json.dumps(missing)

    @app.route("/filter/<course_id>/", methods=["GET"])
    @lti_required(role="staff")
    def filter(course_id=None):
        """
        Display a filtered and paginated list of students in the course.

        :param course_id: The Canvas ID of the course to search in
        :type: int
        :rtype: str
        :returns: A list of students in the course using the template user_list.html.
        """

        query = request.args.get("query", "").lower()

        course = canvas.get_course(course_id)
        user_list = course.get_users(
            search_term=query,
            enrollment_type=["student"],
            enrollment_state=["active", "invited"],
        )

        return render_template("user_list.html", users=user_list)


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
            course_obj = canvas.get_course(course_id)
        except ResourceDoesNotExist:
            update_job(job, 0, "Course not found.", "failed", error=True)
            logger.exception("Unable to find course #{}".format(course_id))
            return job.meta

        course_name = course_obj.name

        user_ids = extension_dict.get("user_ids", [])

        # New Quizzes requires an int-type ID
        user_ids = [int(id) for id in user_ids]

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
                canvas_user = course_obj.get_user(user_id)
                sortable_name = canvas_user.name

                sis_id = canvas_user.sis_user_id

            except ResourceDoesNotExist:
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

        quizzes = list(course_obj.get_quizzes())

        # New Quizzes might not be implemented on a given installation
        try:
            new_quizzes = list(course_obj.get_new_quizzes())
        except CanvasException:
            logger.error(
                "Error fetching New Quizzes. Your Canvas installation may not support them."
            )
            new_quizzes = []

        all_quizzes = quizzes + new_quizzes

        total_quizzes = len(all_quizzes)

        quiz_time_list = []
        unchanged_quiz_time_list = []

        if total_quizzes < 1:
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

        for index, quiz in enumerate(all_quizzes):
            # Is true if the quiz is a New Quiz
            is_new = isinstance(quiz, NewQuiz)

            # Add time_limit attribute to quiz
            if is_new:
                settings = quiz.quiz_settings
                if settings is not None and settings["has_time_limit"]:
                    # Divide by 60 because Canvas stores new quiz timers in seconds
                    quiz.time_limit = settings["session_time_limit_in_seconds"] / 60
                else:
                    quiz.time_limit = 0

            quiz_id = quiz.id
            quiz_title = quiz.title

            comp_perc = int(((float(index)) / float(total_quizzes)) * 100)
            updating_str = "Updating quiz #{} - {} [{} of {}]"
            update_job(
                job,
                comp_perc,
                updating_str.format(quiz_id, quiz_title, index + 1, total_quizzes),
                "processing",
                error=False,
            )

            extension_response = extend_quiz(quiz, is_new, percent, user_ids)

            if extension_response.get("success", False) is True:
                # add/update quiz
                quiz_obj, created = get_or_create(
                    db.session, Quiz, canvas_id=quiz_id, course_id=course.id
                )
                quiz_obj.title = quiz_title
                quiz_obj.time_limit = quiz.time_limit

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
            # Get course object, refresh name
            course_obj = canvas.get_course(course_id)
            course_name = course_obj.name
            course.course_name = course_name
            db.session.commit()
        except ResourceDoesNotExist:
            update_job(job, 0, "Course not found.", "failed", error=True)
            logger.exception("Unable to find course #{}".format(course_id))

            return job.meta

        # Return both legacy and new quizzes
        quizzes = missing_and_stale_quizzes(canvas, course_id)

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
                canvas_user = course_obj.get_user(user_canvas_id)

                # Skip user if not a student. Fixes an edge case where a
                # student that previously recieved an extension changes roles.
                enrolls = list(canvas_user.get_enrollments())
                type_list = [
                    e.type
                    for e in enrolls
                    if e.enrollment_state in ("active", "invited")
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

            except ResourceDoesNotExist:
                log_str = "User #{} not in course #{}. Deactivating extension #{}."
                logger.info(log_str.format(user_canvas_id, course_id, extension.id))
                extension.active = False
                db.session.commit()
                inactive_list.append(extension.user.sortable_name)
                continue

            # Maps percentage amounts of extensions to their users
            percent_user_map[extension.percent].append(user_canvas_id)

        if len(percent_user_map) < 1:
            msg_str = "No active extensions were found.<br>"
            if len(inactive_list) > 0:
                msg_str += "Extensions for the following students are inactive:<br>{}"
                msg_str = msg_str.format("<br>".join(inactive_list))

            update_job(job, 100, msg_str, "complete", error=False)
            return job.meta

        for index, quiz in enumerate(quizzes):
            # Is true if the quiz is a New Quiz
            is_new = isinstance(quiz, NewQuiz)

            quiz_id = quiz.id
            quiz_title = quiz.title

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
                extension_response = extend_quiz(quiz, is_new, percent, user_list)

                if extension_response.get("success", False) is True:
                    # add/update quiz
                    quiz_obj, created = get_or_create(
                        db.session, Quiz, canvas_id=quiz_id, course_id=course.id
                    )
                    quiz_obj.title = quiz_title
                    quiz_obj.time_limit = quiz.time_limit

                    db.session.commit()
                else:
                    error_message = "Some quizzes couldn't be updated. "
                    error_message += extension_response.get("message", "")
                    update_job(job, comp_perc, error_message, "failed", error=True)
                    return job.meta

        msg = "{} quizzes have been updated.".format(len(quizzes))
        update_job(job, 100, msg, "complete", error=False)
        return job.meta


init_views(app)
