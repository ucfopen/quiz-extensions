# -*- coding: utf-8 -*-

import logging
import math
from logging.config import dictConfig

import config
from canvasapi import Canvas
from canvasapi.exceptions import CanvasException
from canvasapi.new_quiz import NewQuiz
from models import Quiz

dictConfig(config.LOGGING_CONFIG)
logger = logging.getLogger("app")


def extend_quiz(quiz, is_new: bool, percent, user_id_list):
    """
    Extends a quiz time by a percentage for a list of users.

    :param quiz: A quiz object from Canvas
    :type quiz: Quiz | NewQuiz
    :param is_new: Flag for if we are extending a either Classic or New Quiz.
    :type is_new: bool
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
    # Debugging tag for new/classic quiz
    tag = "New" if is_new else "Classic"

    quiz_id = quiz.id
    time_limit = getattr(quiz, "time_limit", 0)

    if time_limit is None or time_limit < 1:
        msg = tag + " Quiz #{} has no time limit, so there is no time to add."
        return {"success": True, "message": msg.format(quiz_id), "added_time": None}

    added_time = int(
        math.ceil(time_limit * ((float(percent) - 100) / 100) if percent else 0)
    )

    quiz_extensions = []

    for user_id in user_id_list:
        user_extension = {"user_id": user_id, "extra_time": added_time}
        quiz_extensions.append(user_extension)

    try:
        # Change accomodation function based on if this is a new quiz
        if is_new:
            quiz.set_accommodations(quiz_extensions)
        else:
            quiz.set_extensions(quiz_extensions)
    except Exception as err:
        msg = (
            "Error creating extension for " + tag + " Quiz #{}. Canvas status code: {}"
        )
        return {
            "success": False,
            "message": msg.format(quiz_id, err),
            "added_time": None,
        }

    msg = "Successfully added {} minutes to " + tag + " Quiz #{}"
    return {
        "success": True,
        "message": msg.format(added_time, quiz_id),
        "added_time": added_time,
    }


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


def missing_and_stale_quizzes(canvas: Canvas, course_id, quickcheck=False):
    """
    Find all quizzes that are in Canvas but not in the database (missing),
    or have an old time limit (stale)

    :param canvas: The Canvas API object.
    :type canvas: Canvas
    :param course_id: The Canvas ID of the Course.
    :type course_id: int
    :param quickcheck: Setting this to `True` will return when the
        first missing or stale quiz is found.
    :type quickcheck: bool
    :rtype: list
    :returns: A list of dictionaries representing missing quizzes. If
        quickcheck is true, only the first missing/stale result is returned.
    """
    course_obj = canvas.get_course(course_id)
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

    missing_list = []

    for index, canvas_quiz in enumerate(all_quizzes):
        # Is true if the quiz is a New Quiz
        is_new = isinstance(canvas_quiz, NewQuiz)

        # Add time_limit attribute to quiz
        if is_new:
            settings = canvas_quiz.quiz_settings
            if settings is not None and settings["has_time_limit"]:
                # Divide by 60 because Canvas stores new quiz timers in seconds
                canvas_quiz.time_limit = settings["session_time_limit_in_seconds"] / 60
            else:
                canvas_quiz.time_limit = 0

        quiz = Quiz.query.filter_by(canvas_id=canvas_quiz.id).first()

        # quiz is missing or time limit has changed
        if not quiz or quiz.time_limit != canvas_quiz.time_limit:
            missing_list.append(canvas_quiz)

            if quickcheck:
                # Found one! Quickcheck complete.
                break

    return missing_list


def update_job(job, percent, status_msg, status, error=False):
    job.meta["percent"] = percent
    job.meta["status"] = status
    job.meta["status_msg"] = status_msg
    job.meta["error"] = error

    job.save()
