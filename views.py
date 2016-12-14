from flask import Flask, render_template, session, request, redirect, url_for, Response
from flask_migrate import Migrate
from functools import wraps

from collections import defaultdict
import requests
import json

# OAuth specific
from ims_lti_py import ToolProvider
from time import time

from models import db, Course, Extension, Quiz, User
from utils import (
    extend_quiz, get_course, get_or_create, get_quizzes, get_user,
    missing_quizzes, search_students
)
import config

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = config.SQLALCHEMY_TRACK_MODIFICATIONS
app.secret_key = config.SECRET_KEY

db.init_app(app)
migrate = Migrate(app, db)

oauth_creds = {config.LTI_KEY: config.LTI_SECRET}

json_headers = {'Authorization': 'Bearer ' + config.API_KEY, 'Content-type': 'application/json'}


def check_valid_user(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        """
        Decorator to check if the user is allowed access to the app.

        If user is allowed, return the decorated function.
        Otherwise, return an error page with corresponding message.
        """
        canvas_user_id = session.get('canvas_user_id')
        lti_logged_in = session.get('lti_logged_in', False)
        if not lti_logged_in or not canvas_user_id:
            return render_template(
                'error.html',
                message='Not allowed!'
            )
        if 'course_id' not in kwargs.keys():
            return render_template(
                'error.html',
                message='No course_id provided.'
            )
        course_id = int(kwargs.get('course_id'))

        if not session.get('is_admin', False):
            enrollments_url = "%scourses/%s/enrollments" % (config.API_URL, course_id)

            payload = {
                'user_id': canvas_user_id,
                'type': ['TeacherEnrollment', 'TaEnrollment', 'DesignerEnrollment']
            }

            user_enrollments_response = requests.get(
                enrollments_url,
                data=json.dumps(payload),
                headers=json_headers
            )
            user_enrollments = user_enrollments_response.json()

            if not user_enrollments or 'errors' in user_enrollments:
                message = 'You are not enrolled in this course as a Teacher, TA, or Designer.'
                return render_template(
                    'error.html',
                    message=message
                )

        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def add_google_analytics_id():
    return dict(GOOGLE_ANALYTICS=config.GOOGLE_ANALYTICS)


@app.route("/", methods=['POST', 'GET'])
def index():
    """
    Default app index.
    """
    return "Please contact your System Administrator."


@app.route("/lti.xml", methods=['GET'])
def xml():
    """
    Returns the lti.xml file for the app.
    """
    from urlparse import urlparse
    domain = urlparse(request.url_root).netloc

    return Response(
        render_template(
            'lti.xml',
            tool_id=config.LTI_TOOL_ID,
            domain=domain,
        ),
        mimetype='application/xml'
    )


@app.route("/quiz/<course_id>/", methods=['GET'])
@check_valid_user
def quiz(course_id=None):
    """
    Main landing page for the app.

    Displays a page to the user that allows them to select students
    to moderate quizzes for.
    """
    return render_template(
        'userselect.html',
        course_id=course_id,
        current_page_number=1
    )


@app.route("/update/<course_id>/", methods=['POST'])
@check_valid_user
def update(course_id=None):
    """
    Processes requests to update time on selected students' quizzes to
    a specified percentage.

    Accepts a JSON formatted object that includes the percent of time
    and a list of canvas user ids.

    Example:
    {
        "percent": "300",
        "user_ids": [
            "0123456",
            "1234567",
            "9867543",
            "5555555"
        ]
    }
    """
    post_json = request.get_json()

    if not post_json:
        return json.dumps({
            "error": True,
            "message": "invalid request"
        })

    try:
        course_json = get_course(course_id)
    except requests.exceptions.HTTPError:
        return json.dumps({
            'error': True,
            'message': 'Course not found.'
        })

    course_name = course_json.get('name', '<UNNAMED COURSE>')

    user_ids = post_json.get('user_ids', [])
    percent = post_json.get('percent', None)

    if not percent:
        return json.dumps({
            "error": True,
            "message": "percent required"
        })

    if len(missing_quizzes(course_id, True)) > 0:
        # Some quizzes are missing. Refresh first.
        refresh_status = json.loads(refresh(course_id=course_id))
        if refresh_status.get('success', False) is False:
            return json.dumps({
                "error": True,
                "message": refresh_status.get(
                    'message',
                    "Detected missing quizzes. Attempted to update, but an unknown error occured."
                )
            })

    course, created = get_or_create(db.session, Course, canvas_id=course_id)
    course.course_name = course_name
    db.session.commit()

    for user_id in user_ids:
        try:
            canvas_user = get_user(user_id)

            sortable_name = canvas_user.get('sortable_name', '<MISSING NAME>')
            sis_id = canvas_user.get('sis_user_id')

        except requests.exceptions.HTTPError:
            # unable to find user
            continue

        user, created = get_or_create(db.session, User, canvas_id=user_id)

        user.sortable_name = sortable_name
        user.sis_id = sis_id

        db.session.commit()

        # create/update extension
        extension, created = get_or_create(
            db.session,
            Extension,
            course_id=course.id,
            user_id=user.id
        )
        extension.percent = percent

        db.session.commit()

    quizzes = get_quizzes(course_id)
    num_quizzes = len(quizzes)
    quiz_time_list = []
    unchanged_quiz_time_list = []

    if num_quizzes < 1:
        return json.dumps({
            "error": True,
            "message": "Sorry, there are no quizzes for this course."
        })

    for quiz in quizzes:
        quiz_id = quiz.get('id', None)
        quiz_title = quiz.get('title', "[UNTITLED QUIZ]")

        extension_response = extend_quiz(course_id, quiz, percent, user_ids)
        if extension_response.get('success', False) is True:
            # add/update quiz
            quiz_obj, created = get_or_create(
                db.session,
                Quiz,
                canvas_id=quiz_id,
                course_id=course.id
            )
            quiz_obj.title = quiz_title

            db.session.commit()

            added_time = extension_response.get('added_time', None)
            if added_time is not None:
                quiz_time_list.append({
                    "title": quiz_title,
                    "added_time": added_time
                })
            else:
                unchanged_quiz_time_list.append({"title": quiz_title})
        else:
            return json.dumps({
                'error': True,
                'message': extension_response.get('message', 'An unknown error occured')
            })

    msg_str = (
        'Success! {} {} been updated for {} student(s) to have {}% time. '
        '{} {} no time limit and were left unchanged.'
    )

    message = msg_str.format(
        len(quiz_time_list),
        "quizzes have" if len(quiz_time_list) != 1 else "quiz has",
        len(user_ids),
        percent,
        len(unchanged_quiz_time_list),
        "quizzes have" if len(unchanged_quiz_time_list) != 1 else "quiz has"
    )

    return json.dumps({
        "error": False,
        "message": message,
        "quiz_list": quiz_time_list,
        "unchanged_list": unchanged_quiz_time_list
    })


@app.route("/refresh/<course_id>/", methods=['POST'])
@check_valid_user
def refresh(course_id=None):
    """
    Look up existing extensions and apply them to new quizzes.

    :param course_id: The Canvas ID of the Course.
    :type course_id: int
    :rtype: str
    :returns: A JSON-formatted string representation of an object
        containing two parts:

        - success `bool` false if there was an error, true otherwise.
        - message `str` A long description of success or failure.
    """
    course, created = get_or_create(db.session, Course, canvas_id=course_id)

    try:
        course_name = get_course(course_id).get('name', '<UNNAMED COURSE>')
        course.course_name = course_name
        db.session.commit()
    except requests.exceptions.HTTPError:
        return json.dumps({
            'success': False,
            'message': 'Course not found.'
        })

    # quiz stuff
    quizzes = missing_quizzes(course_id)

    if len(quizzes) < 1:
        return json.dumps({
            'success': True,
            'message': 'No quizzes require updates.'
        })

    percent_user_map = defaultdict(list)
    for extension in course.extensions:
        user_canvas_id = User.query.filter_by(id=extension.user_id).first().canvas_id
        percent_user_map[extension.percent].append(user_canvas_id)

    for quiz in quizzes:
        quiz_id = quiz.get('id', None)
        quiz_title = quiz.get('title', "[UNTITLED QUIZ]")

        for percent, user_list in percent_user_map.iteritems():
            extension_response = extend_quiz(course_id, quiz, percent, user_list)

            if extension_response.get('success', False) is True:
                quiz_obj = Quiz(quiz_id, course.id, quiz_title)
                db.session.add(quiz_obj)
                db.session.commit()
            else:
                error_message = extension_response.get('message', '')
                return json.dumps({
                    'success': False,
                    'message': 'Some quizzes couldn\'t be updated. ' + error_message
                })

    return json.dumps({
        'success': True,
        'message': '{} quizzes have been updated.'.format(len(quizzes))
    })


@app.route("/missing_quizzes/<course_id>/", methods=['GET'])
def missing_quizzes_check(course_id):
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
        return 'false'

    num_extensions = Extension.query.filter_by(course_id=course.id).count()
    if num_extensions == 0:
        # There are no extensions for this course yet. No need to update.
        return 'false'

    missing = len(missing_quizzes(course_id, True)) > 0
    return json.dumps(missing)


@app.route("/filter/<course_id>/", methods=['GET'])
@check_valid_user
def filter(course_id=None):
    """
    Display a filtered and paginated list of students in the course.

    :param course_id:
    :type: int
    :rtype: str
    :returns: A list of students in the course using the template
        user_list.html.
    """

    query = request.args.get('query', '').lower()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', config.DEFAULT_PER_PAGE))

    user_list, max_pages = search_students(
        course_id,
        per_page=per_page,
        page=page,
        search_term=query
    )

    if not user_list or max_pages < 1:
        user_list = []
        max_pages = 1

    return render_template(
        'user_list.html',
        users=user_list,
        current_page_number=page,
        max_pages=max_pages
    )


@app.route('/launch', methods=['POST'])
def lti_tool():
    """
    Bootstrapper for lti.
    """
    course_id = request.form.get('custom_canvas_course_id')
    canvas_user_id = request.form.get('custom_canvas_user_id')

    roles = request.form.get('ext_roles', [])
    if "Administrator" not in roles and "Instructor" not in roles:
        return render_template(
            'error.html',
            message='Must be an Administrator or Instructor',
            params=request.form
        )

    session["is_admin"] = "Administrator" in roles

    key = request.form.get('oauth_consumer_key')
    if key:
        secret = oauth_creds.get(key)
        if secret:
            tool_provider = ToolProvider(key, secret, request.form)
        else:
            tool_provider = ToolProvider(None, None, request.form)
            tool_provider.lti_msg = 'Your consumer didn\'t use a recognized key'
            tool_provider.lti_errorlog = 'You did it wrong!'
            return render_template(
                'error.html',
                message='Consumer key wasn\'t recognized',
                params=request.form
            )
    else:
        return render_template('error.html', message='No consumer key')
    if not tool_provider.is_valid_request(request):
        return render_template(
            'error.html',
            message='The OAuth signature was invalid',
            params=request.form
        )

    if time() - int(tool_provider.oauth_timestamp) > 60*60:
        return render_template('error.html', message='Your request is too old.')

    # This does truly check anything, it's just here to remind you  that real
    # tools should be checking the OAuth nonce
    if was_nonce_used_in_last_x_minutes(tool_provider.oauth_nonce, 60):
        return render_template('error.html', message='Why are you reusing the nonce?')

    session['canvas_user_id'] = canvas_user_id
    session['lti_logged_in'] = True

    session['launch_params'] = tool_provider.to_params()
    username = tool_provider.username('Dude')

    if tool_provider.is_outcome_service():
        return render_template('assessment.html', username=username)
    else:
        return redirect(url_for('quiz', course_id=course_id))


def was_nonce_used_in_last_x_minutes(nonce, minutes):
    return False
