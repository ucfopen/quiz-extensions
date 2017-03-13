from collections import defaultdict
import json
import math
import requests
from urlparse import parse_qs, urlsplit

import config
from models import Quiz

import logging
from logging.config import dictConfig

dictConfig(config.LOGGING_CONFIG)
logger = logging.getLogger('app')

headers = {'Authorization': 'Bearer ' + config.API_KEY}
json_headers = {'Authorization': 'Bearer ' + config.API_KEY, 'Content-type': 'application/json'}


def extend_quiz(course_id, quiz, percent, user_id_list):
    """
    Extends a quiz time by a percentage for a list of users.

    :param quiz: A quiz object from Canvas
    :type quiz: dict
    :param percent: The percent of original quiz time to be applied.
        e.g. 200 is double time, 100 is normal time, <100 is invalid.
    :type percent: int
    :param user_id_list: A list of Canvas user IDs to add time for.
    :type user_id_list: list
    :rtype: dict
    :returns: A dictionary with three parts:

        - success `bool` False if there was an error, True otherwise.
        - message `str` A long description of success or failure.
        - added_time `int` The amount of time added in minutes. Returns
        `None` if there was no time added.
    """
    quiz_id = quiz.get('id')
    time_limit = quiz.get('time_limit')

    if time_limit is None or time_limit < 1:
        msg = 'Quiz #{} has no time limit, so there is no time to add.'
        return {
            'success': True,
            'message': msg.format(quiz_id),
            'added_time': None
        }

    added_time = int(math.ceil(time_limit * ((float(percent)-100) / 100) if percent else 0))

    quiz_extensions = defaultdict(list)

    for user_id in user_id_list:
        user_extension = {
            'user_id': user_id,
            'extra_time': added_time
        }
        quiz_extensions['quiz_extensions'].append(user_extension)

    extensions_response = requests.post(
        "%scourses/%s/quizzes/%s/extensions" % (config.API_URL, course_id, quiz_id),
        data=json.dumps(quiz_extensions),
        headers=json_headers
    )

    if extensions_response.status_code == 200:
        msg = 'Successfully added {} minutes to quiz #{}'
        return {
            'success': True,
            'message': msg.format(added_time, quiz_id),
            'added_time': added_time
        }
    else:
        msg = 'Error creating extension for quiz #{}. Canvas status code: {}'
        return {
            'success': False,
            'message': msg.format(quiz_id, extensions_response.status_code),
            'added_time': None
        }


def get_quizzes(course_id, per_page=config.MAX_PER_PAGE):
    """
    Get all quizzes in a Canvas course.

    :param course_id: The Canvas ID of a Course
    :type course_id: int
    :param per_page: The number of quizzes to get per page.
    :type per_page: int
    :rtype: list
    :returns: A list of dictionaries representing Canvas Quiz objects.
    """
    quizzes = []
    quizzes_url = "%scourses/%s/quizzes?per_page=%d" % (config.API_URL, course_id, per_page)

    while True:
        quizzes_response = requests.get(quizzes_url, headers=headers)

        quizzes_list = quizzes_response.json()

        if 'errors' in quizzes_list:
            break

        quizzes.extend(quizzes_list)

        try:
            quizzes_url = quizzes_response.links['next']['url']
        except KeyError:
            break

    return quizzes


def search_students(course_id, per_page=config.DEFAULT_PER_PAGE, page=1, search_term=""):
    """
    Search for students in the course.

    If no search term is provided, all users are returned.

    :param course_id: The Canvas ID of a Course.
    :type course_id: int
    :param per_page: The number of students to get
    :type per_page: int
    :param page: The page number to get
    :type page: int
    :param search_term: A string to filter students by
    :type search_term: str
    """
    users_url = "%scourses/%s/search_users?per_page=%s&page=%s&access_token=%s" % (
        config.API_URL,
        course_id,
        per_page,
        page,
        config.API_KEY
    )

    users_response = requests.get(
        users_url,
        data={
            'search_term': search_term,
            'enrollment_type': 'student'
        },
        headers=headers,
    )

    try:
        user_list = users_response.json()
    except ValueError:
        # response is weird. log it!
        logger.exception('Error getting user list from Canvas.')
        return [], 0

    if 'errors' in user_list:
        msg = 'Error getting user list from Canvas. Response: {}'
        logger.error(msg.format(users_response))
        return [], 0

    try:
        num_pages = int(
            parse_qs(
                urlsplit(
                    users_response.links['last']['url']
                ).query
            )['page'][0]
        )
    except KeyError:
        num_pages = 0

    return user_list, num_pages


def get_user(course_id, user_id):
    """
    Get a user from canvas by id, with respect to a course.

    :param user_id: ID of a Canvas course.
    :type user_id: int
    :param user_id: ID of a Canvas user.
    :type user_id: int
    :rtype: dict
    :returns: A dictionary representation of a User in Canvas.
    """
    response = requests.get(
        '{}courses/{}/users/{}'.format(
            config.API_URL,
            course_id,
            user_id
        ),
        headers=headers
    )
    response.raise_for_status()

    return response.json()


def get_course(course_id):
    """
    Get a course from canvas by id.

    :param course_id: ID of a Canvas course.
    :type course_id: int
    :rtype: dict
    :returns: A dictionary representation of a Course in Canvas.
    """
    response = requests.get(config.API_URL + 'courses/' + str(course_id), headers=headers)
    response.raise_for_status()

    return response.json()


def get_or_create(session, model, **kwargs):
    """
    Simple version of Django's get_or_create for interacting with Models

    :param session: SQLAlchemy database session
    :type session: :class:`sqlalchemy.orm.scoping.scoped_session`
    :param model: The model to get or create from.
    :type model: :class:`flask_sqlalchemy.Model`
    """
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance, False
    else:
        instance = model(**kwargs)
        session.add(instance)
        session.commit()
        return instance, True


def missing_quizzes(course_id, quickcheck=False):
    """
    Find all quizzes that are in Canvas but not in the database.

    :param course_id: The Canvas ID of the Course.
    :type course_id: int
    :param quickcheck: Setting this to `True` will return when the
        first missinq quiz is found.
    :type quickcheck: bool
    :rtype: list
    :returns: A list of dictionaries representing missing quizzes. If
        quickcheck is true, only the first result is returned.
    """
    quizzes = get_quizzes(course_id)

    missing_list = []

    for canvas_quiz in quizzes:
        quiz = Quiz.query.filter_by(canvas_id=canvas_quiz.get('id')).first()

        if quiz:
            # Already exists. Next!
            continue

        missing_list.append(canvas_quiz)

        if quickcheck:
            # Found one! Quickcheck complete.
            break

    return missing_list
