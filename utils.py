import requests
from urlparse import parse_qs, urlsplit

import config


headers = {'Authorization': 'Bearer ' + config.API_KEY}


def get_quizzes(course_id, per_page=config.MAX_PER_PAGE):
    """
    Returns a list of all quizzes in the course.
    """
    quizzes = []
    quizzes_url = "%scourses/%s/quizzes?per_page=%d" % (config.API_URL, course_id, per_page)

    while True:
        quizzes_response = requests.get(quizzes_url, headers=headers)

        quizzes_list = quizzes_response.json()

        if 'errors' in quizzes_list:
            break

        if isinstance(quizzes_list, list):
            quizzes.extend(quizzes_list)
        else:
            quizzes = quizzes_list

        try:
            quizzes_url = quizzes_response.links['next']['url']
        except KeyError:
            break

    return quizzes


def search_users(course_id, per_page=config.DEFAULT_PER_PAGE, page=1, search_term=""):
    """
    Searches for students in the course.

    If no search term is provided, all users are returned.
    """
    users_url = "%s/courses/%s/search_users?per_page=%s&page=%s" % (
        config.API_URL,
        course_id,
        per_page,
        page
    )

    users_response = requests.get(
        users_url,
        data={
            'search_term': search_term,
            'enrollment_type': 'student'
        },
        headers=headers
    )
    user_list = users_response.json()

    if 'errors' in user_list:
        return [], 0

    num_pages = int(
        parse_qs(
            urlsplit(
                users_response.links['last']['url']
            ).query
        )['page'][0]
    )

    return user_list, num_pages


def get_user(user_id):
    """
    Get a user from canvas by id.

    :param user_id: ID of a Canvas user.
    :type user_id: int
    :rtype: dict
    :returns: A dictionary representation of a User in Canvas.
    """
    response = requests.get(config.API_URL + 'users/' + user_id, headers=headers)
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
    response = requests.get(config.API_URL + 'courses/' + course_id, headers=headers)
    response.raise_for_status()

    return response.json()


def get_or_create(session, model, **kwargs):
    """
    Simple version of Django's get_or_create for interacting with Models
    """
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance, False
    else:
        instance = model(**kwargs)
        session.add(instance)
        session.commit()
        return instance, True
