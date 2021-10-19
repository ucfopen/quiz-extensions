# -*- coding: utf-8 -*-
import logging
from unittest.mock import patch
from urllib.parse import urlencode

import fakeredis
import flask_testing
import oauthlib.oauth1
import requests
import requests_mock
from flask import session, url_for
from pylti.common import LTI_SESSION_KEY
from rq import Queue, SimpleWorker

import config
import views
from models import Course, Extension, Quiz, User


@requests_mock.Mocker()
class ViewTests(flask_testing.TestCase):
    def create_app(self):
        app = views.app
        app.config["TESTING"] = True
        app.config["DEBUG"] = False
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/test.db"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        return app

    def setUp(self):
        views.db.init_app(self.app)
        with self.app.test_request_context():
            views.db.create_all()

        self.queue = Queue(is_async=False, connection=fakeredis.FakeStrictRedis())
        self.worker = SimpleWorker([self.queue], connection=self.queue.connection)

    def tearDown(self):
        views.db.session.remove()
        views.db.drop_all()

    @classmethod
    def setUpClass(cls):
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        logging.disable(logging.NOTSET)

    def test_check_valid_user_no_canvas_user_id(self, m):
        @views.check_valid_user
        def test_func():
            pass  # pragma: no cover

        response = test_func()
        self.assert_template_used("error.html")
        self.assertIn("Not allowed!", response)

    def test_check_valid_user_no_lti_logged_in(self, m):
        session["canvas_user_id"] = 1234

        @views.check_valid_user
        def test_func():
            pass  # pragma: no cover

        response = test_func()

        self.assert_template_used("error.html")
        self.assertIn("Not allowed!", response)

    def test_check_valid_user_no_course_id(self, m):
        session["canvas_user_id"] = 1234
        session["lti_logged_in"] = True

        @views.check_valid_user
        def test_func():
            pass  # pragma: no cover

        response = test_func()

        self.assert_template_used("error.html")
        self.assertIn("No course_id provided.", response)

    def test_check_valid_user_is_admin(self, m):
        session["canvas_user_id"] = 1234
        session["lti_logged_in"] = True
        session["is_admin"] = True

        @views.check_valid_user
        def test_func(**kwargs):
            return "Course ID: {}".format(kwargs.get("course_id"))

        response = test_func(course_id=1)

        self.assertEqual("Course ID: 1", response)

    def test_check_valid_user_no_enrollments(self, m):
        m.register_uri("GET", "/api/v1/courses/1/enrollments", json=[])

        session["canvas_user_id"] = 1234
        session["lti_logged_in"] = True

        @views.check_valid_user
        def test_func(**kwargs):
            pass  # pragma: no cover

        response = test_func(course_id=1)

        self.assert_template_used("error.html")
        self.assertIn(
            "You are not enrolled in this course as a Teacher, TA, or Designer.",
            response,
        )

    def test_check_valid_user_success(self, m):
        m.register_uri(
            "GET",
            "/api/v1/courses/1/enrollments",
            json=[
                {"id": 1, "course_id": 1, "user_id": 1234, "role": "TeacherEnrollment"}
            ],
        )

        session["canvas_user_id"] = 1234
        session["lti_logged_in"] = True

        @views.check_valid_user
        def test_func(**kwargs):
            return "Course ID: {}".format(kwargs.get("course_id"))

        response = test_func(course_id=1)

        self.assertEqual("Course ID: 1", response)

    def test_index(self, m):
        response = self.client.get("/")
        self.assertEqual(response.data, b"Please contact your System Administrator.")

    def test_xml(self, m):
        response = self.client.get("/lti.xml")

        self.assert_200(response)
        self.assert_template_used("lti.xml")
        self.assertIn("application/xml", response.content_type)

        self.assert_context("tool_id", config.LTI_TOOL_ID)
        self.assertIn(url_for("lti_tool").encode("utf-8"), response.data)

    def test_quiz(self, m):
        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True
            sess[LTI_SESSION_KEY] = True
            sess["roles"] = "urn:lti:instrole:ims/lis/Administrator"

        course_id = 1

        response = self.client.get("/quiz/{}/".format(course_id))

        self.assert_200(response)
        self.assert_template_used("userselect.html")
        self.assertEqual(self.get_context_variable("course_id"), str(course_id))
        self.assertEqual(self.get_context_variable("current_page_number"), 1)

    def test_update_background_no_json(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1

        job = self.queue.enqueue_call(func=update_background, args=(course_id, None))
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.result

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(job_result["status_msg"], "Invalid Request")

    def test_update_background_no_course(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1

        m.register_uri("GET", "/api/v1/courses/1", status_code=404)

        job = self.queue.enqueue_call(
            func=update_background,
            args=(course_id, {"percent": "200", "user_ids": ["11", "12"]}),
        )
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.result

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(job_result["status_msg"], "Course not found.")

    def test_update_background_no_percent(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1

        m.register_uri(
            "GET", "/api/v1/courses/1", json={"id": 1, "name": "Example Course"}
        )

        job = self.queue.enqueue_call(
            func=update_background, args=(course_id, {"user_ids": ["11", "12"]})
        )
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.result

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(job_result["status_msg"], "`percent` field required.")

    def test_update_background_refresh_error(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1

        m.register_uri(
            "GET", "/api/v1/courses/1", json={"id": 1, "name": "Example Course"}
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json=[
                {"id": 4, "title": "Quiz 4", "time_limit": 10},
                {"id": 5, "title": "Quiz 5", "time_limit": 30},
            ],
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/users/11",
            json={
                "id": 11,
                "sortable_name": "Joe Smyth",
                "enrollments": [
                    {"type": "StudentEnrollment", "enrollment_state": "active"}
                ],
            },
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/users/12",
            json={
                "id": 12,
                "sortable_name": "Jack Smith",
                "enrollments": [
                    {"type": "StudentEnrollment", "enrollment_state": "active"}
                ],
            },
        )
        m.register_uri(
            "POST", "/api/v1/courses/1/quizzes/4/extensions", status_code=404
        )

        course = Course(course_id, course_name="Example Course")
        views.db.session.add(course)

        user = User(11, sortable_name="Joe Smyth")
        views.db.session.add(user)
        user2 = User(12, sortable_name="Jack Smith")
        views.db.session.add(user2)

        views.db.session.commit()

        ext = Extension(course.id, user.id)
        views.db.session.add(ext)
        ext2 = Extension(course.id, user2.id)
        views.db.session.add(ext2)

        views.db.session.commit()

        job = self.queue.enqueue_call(
            func=update_background,
            args=(course_id, {"percent": "200", "user_ids": ["11", "12"]}),
        )
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.result

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(
            job_result["status_msg"],
            "Error creating extension for quiz #4. Canvas status code: 404",
        )

    def test_update_background_no_quizzes(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1

        m.register_uri(
            "GET", "/api/v1/courses/1", json={"id": 1, "name": "Example Course"}
        )
        m.register_uri("GET", "/api/v1/courses/1/quizzes", json=[])
        m.register_uri(
            "GET",
            "/api/v1/courses/1/users/11",
            json={"id": 11, "sortable_name": "Joe Smyth"},
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/users/12",
            json={"id": 12, "sortable_name": "Jack Smith"},
        )
        course = Course(course_id, course_name="Example Course")
        views.db.session.add(course)

        user = User(11, sortable_name="Joe Smyth")
        views.db.session.add(user)
        user2 = User(12, sortable_name="Jack Smith")
        views.db.session.add(user2)

        views.db.session.commit()

        ext = Extension(course.id, user.id)
        views.db.session.add(ext)
        ext2 = Extension(course.id, user2.id)
        views.db.session.add(ext2)

        views.db.session.commit()

        job = self.queue.enqueue_call(
            func=update_background,
            args=(course_id, {"percent": "200", "user_ids": ["11", "12"]}),
        )
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.result

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(
            job_result["status_msg"], "Sorry, there are no quizzes for this course."
        )

    def test_update_background_extension_error(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1

        m.register_uri(
            "GET", "/api/v1/courses/1", json={"id": 1, "name": "Example Course"}
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json=[
                {"id": 4, "title": "Quiz 4", "time_limit": 10},
                {"id": 5, "title": "Quiz 5", "time_limit": 30},
                {"id": 6, "title": "Quiz 6", "time_limit": None},
                {"id": 7, "title": "Quiz 7"},
            ],
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/users/11",
            json={"id": 11, "sortable_name": "Joe Smyth"},
        )
        m.register_uri("GET", "/api/v1/courses/1/users/12", status_code=404)
        m.register_uri(
            "GET",
            "/api/v1/courses/1/users/13",
            json={
                "id": 13,
                "sortable_name": "Jack Smith",
                "enrollments": [
                    {"type": "StudentEnrollment", "enrollment_state": "active"}
                ],
            },
        )
        m.register_uri(
            "POST", "/api/v1/courses/1/quizzes/4/extensions", status_code=404
        )
        m.register_uri(
            "POST", "/api/v1/courses/1/quizzes/5/extensions", status_code=200
        )

        course = Course(course_id, course_name="Example Course")
        views.db.session.add(course)

        user = User(11, sortable_name="Joe Smyth")
        views.db.session.add(user)
        user2 = User(13, sortable_name="Jack Smith")
        views.db.session.add(user2)

        views.db.session.commit()

        ext = Extension(course.id, user.id)
        views.db.session.add(ext)
        ext2 = Extension(course.id, user2.id)
        views.db.session.add(ext2)

        views.db.session.commit()

        job = self.queue.enqueue_call(
            func=update_background,
            args=(course_id, {"percent": "200", "user_ids": ["11", "12", "13"]}),
        )
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.result

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(
            job_result["status_msg"],
            "Error creating extension for quiz #4. Canvas status code: 404",
        )

    def test_update_background(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1

        m.register_uri(
            "GET", "/api/v1/courses/1", json={"id": 1, "name": "Example Course"}
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json=[
                {"id": 4, "title": "Quiz 4", "time_limit": 10},
                {"id": 5, "title": "Quiz 5", "time_limit": 30},
                {"id": 6, "title": "Quiz 6", "time_limit": None},
                {"id": 7, "title": "Quiz 7"},
            ],
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/users/11",
            json={"id": 11, "sortable_name": "Joe Smyth"},
        )
        m.register_uri("GET", "/api/v1/courses/1/users/12", status_code=404)
        m.register_uri(
            "GET",
            "/api/v1/courses/1/users/13",
            json={"id": 13, "sortable_name": "Jack Smith"},
        )
        m.register_uri(
            "POST", "/api/v1/courses/1/quizzes/4/extensions", status_code=200
        )
        m.register_uri(
            "POST", "/api/v1/courses/1/quizzes/5/extensions", status_code=200
        )

        course = Course(course_id, course_name="Example Course")
        views.db.session.add(course)

        user = User(11, sortable_name="Joe Smyth")
        views.db.session.add(user)
        user2 = User(13, sortable_name="Jack Smith")
        views.db.session.add(user2)

        views.db.session.commit()

        ext = Extension(course.id, user.id)
        views.db.session.add(ext)
        ext2 = Extension(course.id, user2.id)
        views.db.session.add(ext2)

        views.db.session.commit()

        job = self.queue.enqueue_call(
            func=update_background,
            args=(course_id, {"percent": "200", "user_ids": ["11", "12", "13"]}),
        )
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.result

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "complete")
        self.assertFalse(job_result["error"])
        self.assertEqual(job_result["percent"], 100)
        self.assertEqual(
            job_result["status_msg"],
            (
                "Success! 2 quizzes have been updated for 3 student(s) to have "
                "200% time. 2 quizzes have no time limit and were left unchanged."
            ),
        )

    def test_refresh_background_no_course(self, m):
        from views import refresh_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1

        m.register_uri("GET", "/api/v1/courses/1", status_code=404)

        job = self.queue.enqueue_call(func=refresh_background, args=(course_id,))
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.result

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))
        self.assertEqual(job_result["status"], "failed")
        self.assertEqual(job_result["status_msg"], "Course not found.")
        self.assertEqual(job_result["percent"], 0)
        self.assertTrue(job_result["error"])

    def test_refresh_background_no_missing_and_stale_quizzes(self, m):
        from views import refresh_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1

        m.register_uri(
            "GET", "/api/v1/courses/1", json={"id": 1, "name": "Example Course"}
        )
        m.register_uri(
            "GET", "/api/v1/courses/1/quizzes", json=[{"id": 3, "title": "Quiz 3"}]
        )

        quiz = Quiz(3, course_id)
        views.db.session.add(quiz)
        views.db.session.commit()

        job = self.queue.enqueue_call(func=refresh_background, args=(course_id,))
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.result

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "complete")
        self.assertEqual(
            job_result["status_msg"], "Complete. No quizzes required updates."
        )
        self.assertEqual(job_result["percent"], 100)
        self.assertFalse(job_result["error"])

    def test_refresh_background_update_error(self, m):
        from views import refresh_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1

        m.register_uri(
            "GET",
            "/api/v1/courses/{}".format(course_id),
            json={"id": course_id, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json=[{"id": 1, "title": "Quiz 1", "time_limit": 10}],
        )
        m.register_uri(
            "POST", "/api/v1/courses/1/quizzes/1/extensions", status_code=404
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/users/12345",
            json={
                "id": 12345,
                "sortable_name": "John Smith",
                "enrollments": [
                    {"type": "StudentEnrollment", "enrollment_state": "active"}
                ],
            },
        )

        course = Course(course_id, course_name="Example Course")
        views.db.session.add(course)

        user = User(12345, sortable_name="John Smith")
        views.db.session.add(user)

        views.db.session.commit()

        ext = Extension(course.id, user.id)
        views.db.session.add(ext)
        views.db.session.commit()

        job = self.queue.enqueue_call(func=refresh_background, args=(course_id,))
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.result

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(
            job_result["status_msg"],
            (
                "Some quizzes couldn't be updated. Error creating extension "
                "for quiz #1. Canvas status code: 404"
            ),
        )

    def test_refresh_background_missing_user(self, m):
        from views import refresh_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1
        user_id = 9001

        m.register_uri(
            "GET",
            "/api/v1/courses/{}".format(course_id),
            json={"id": course_id, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/{}/quizzes".format(course_id),
            json=[
                {"id": 1, "title": "Quiz 1", "time_limit": 10},
                {"id": 2, "title": "Quiz 2", "time_limit": 30},
            ],
        )
        m.register_uri(
            "POST",
            "/api/v1/courses/{}/quizzes/1/extensions".format(course_id),
            status_code=200,
        )
        m.register_uri(
            "POST",
            "/api/v1/courses/{}/quizzes/2/extensions".format(course_id),
            status_code=200,
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/{}/users/{}".format(course_id, user_id),
            status_code=404,
        )

        course = Course(course_id, course_name="Example Course")
        views.db.session.add(course)
        user = User(user_id, sortable_name="Missing User")
        views.db.session.add(user)

        views.db.session.commit()

        ext = Extension(course.id, user.id)
        views.db.session.add(ext)

        views.db.session.commit()

        # Check that the extension is active first
        self.assertTrue(ext.active)
        ext_id = ext.id

        job = self.queue.enqueue_call(func=refresh_background, args=(course_id,))
        self.worker.work(burst=True)
        self.assertTrue(job.is_finished)

        # Ensure extension has been marked as inactive.
        extension = views.db.session.query(Extension).filter_by(id=ext_id).first()
        self.assertFalse(extension.active)

    def test_refresh_background_inactive_user(self, m):
        from views import refresh_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1
        user_id = 9001

        m.register_uri(
            "GET",
            "/api/v1/courses/{}".format(course_id),
            json={"id": course_id, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/{}/quizzes".format(course_id),
            json=[
                {"id": 1, "title": "Quiz 1", "time_limit": 10},
                {"id": 2, "title": "Quiz 2", "time_limit": 30},
            ],
        )
        m.register_uri(
            "POST",
            "/api/v1/courses/{}/quizzes/1/extensions".format(course_id),
            status_code=200,
        )
        m.register_uri(
            "POST",
            "/api/v1/courses/{}/quizzes/2/extensions".format(course_id),
            status_code=200,
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/{}/users/{}".format(course_id, user_id),
            status_code=200,
            json={
                "id": 9001,
                "sortable_name": "John Smith",
                "enrollments": [
                    {"type": "StudentEnrollment", "enrollment_state": "inactive"}
                ],
            },
        )

        course = Course(course_id, course_name="Example Course")
        views.db.session.add(course)
        user = User(user_id, sortable_name="Missing User")
        views.db.session.add(user)

        views.db.session.commit()

        ext = Extension(course.id, user.id)
        views.db.session.add(ext)

        views.db.session.commit()

        # Check that the extension is active first
        self.assertTrue(ext.active)
        ext_id = ext.id

        job = self.queue.enqueue_call(func=refresh_background, args=(course_id,))
        self.worker.work(burst=True)
        self.assertTrue(job.is_finished)

        # Ensure extension has been marked as inactive.
        extension = views.db.session.query(Extension).filter_by(id=ext_id).first()
        self.assertFalse(extension.active)

    def test_refresh_background_update_success(self, m):
        from views import refresh_background

        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True

        course_id = 1

        m.register_uri(
            "GET",
            "/api/v1/courses/{}".format(course_id),
            json={"id": course_id, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json=[
                {"id": 1, "title": "Quiz 1", "time_limit": 10},
                {"id": 2, "title": "Quiz 2", "time_limit": 30},
            ],
        )
        m.register_uri(
            "POST", "/api/v1/courses/1/quizzes/1/extensions", status_code=200
        )
        m.register_uri(
            "POST", "/api/v1/courses/1/quizzes/2/extensions", status_code=200
        )
        m.register_uri(
            "GET",
            "/api/v1/courses/1/users/12345",
            json={
                "id": 12345,
                "sortable_name": "John Smith",
                "enrollments": [
                    {"type": "StudentEnrollment", "enrollment_state": "active"}
                ],
            },
        )

        course = Course(course_id, course_name="Example Course")
        views.db.session.add(course)

        user = User(12345, sortable_name="John Smith")
        views.db.session.add(user)

        views.db.session.commit()

        ext = Extension(course.id, user.id)
        views.db.session.add(ext)

        # Add an inactive extension to be ignored.
        ext_inactive = Extension(course.id, user.id)
        ext_inactive.active = False
        views.db.session.add(ext_inactive)

        views.db.session.commit()

        job = self.queue.enqueue_call(func=refresh_background, args=(course_id,))
        self.worker.work(burst=True)
        self.assertTrue(job.is_finished)
        job_result = job.result

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "complete")
        self.assertFalse(job_result["error"])
        self.assertEqual(job_result["status_msg"], "2 quizzes have been updated.")
        self.assertEqual(job_result["percent"], 100)

    def test_missing_and_stale_quizzes_check_no_course(self, m):
        course_id = 1
        response = self.client.get("/missing_and_stale_quizzes/{}/".format(course_id))

        self.assert_200(response)
        self.assertEqual(response.data, b"false")

    def test_missing_and_stale_quizzes_check_no_extensions(self, m):
        course_id = 1

        course = Course(canvas_id=course_id, course_name="test")
        views.db.session.add(course)
        views.db.session.commit()

        response = self.client.get("/missing_and_stale_quizzes/{}/".format(course_id))

        self.assert_200(response)
        self.assertEqual(response.data, b"false")

    def test_missing_and_stale_quizzes_check_true(self, m):
        m.register_uri(
            "GET", "/api/v1/courses/1/quizzes", json=[{"id": 1, "title": "Quiz 1"}]
        )

        course_id = 1

        course = Course(canvas_id=course_id, course_name="test")
        views.db.session.add(course)
        views.db.session.commit()

        extension = Extension(course_id=course.id, user_id=5, percent=200)
        views.db.session.add(extension)
        views.db.session.commit()

        response = self.client.get("/missing_and_stale_quizzes/{}/".format(course_id))

        self.assert_200(response)
        self.assertEqual(response.data, b"true")

    def test_missing_and_stale_quizzes_check_false(self, m):
        m.register_uri(
            "GET", "/api/v1/courses/1/quizzes", json=[{"id": 1, "title": "Quiz 1"}]
        )

        course_id = 1

        course = Course(canvas_id=course_id, course_name="test")
        views.db.session.add(course)

        quiz = Quiz(canvas_id=1, course_id=course.id)
        views.db.session.add(quiz)

        views.db.session.commit()

        extension = Extension(course_id=course.id, user_id=5, percent=200)
        views.db.session.add(extension)
        views.db.session.commit()

        response = self.client.get("/missing_and_stale_quizzes/{}/".format(course_id))

        self.assert_200(response)
        self.assertEqual(response.data, b"false")

    def test_filter_no_students_found(self, m):
        with self.client.session_transaction() as sess:
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["is_admin"] = True
            sess["roles"] = "Instructor"
            sess[LTI_SESSION_KEY] = True

        m.register_uri("GET", "/api/v1/courses/1/search_users", json=[])

        course_id = 1
        response = self.client.get("/filter/{}/".format(course_id))
        self.assert_200(response)
        self.assert_template_used("user_list.html")
        self.assertEqual(len(self.get_context_variable("users")), 0)
        self.assertEqual(self.get_context_variable("max_pages"), 1)

    def test_filter(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess["canvas_user_id"] = 1234
            sess["lti_logged_in"] = True
            sess["roles"] = "urn:lti:instrole:ims/lis/Administrator"
            sess["is_admin"] = True

        m.register_uri(
            "GET",
            "/api/v1/courses/1/search_users",
            json=[{"id": 1, "name": "John Smith"}, {"id": 2, "name": "Jane Doe"}],
            headers={
                "Link": '<http://example.com/api/v1/courses/1/search_users?page=99>; rel="last"'
            },
        )

        course_id = 1
        response = self.client.get("/filter/{}/".format(course_id))
        self.assert_200(response)
        self.assert_template_used("user_list.html")
        self.assertEqual(len(self.get_context_variable("users")), 2)
        self.assertEqual(self.get_context_variable("max_pages"), 99)

    def test_lti_tool_not_admin_or_instructor(self, m):
        with self.client.session_transaction() as sess:
            sess[LTI_SESSION_KEY] = True
            sess["oauth_consumer_key"] = "key"
            sess["roles"] = "User"
            sess["canvas_user_id"] = 1

        payload = {
            "launch_presentation_return_url": "http://localhost/",
            "custom_canvas_user_id": "1",
            "custom_canvas_course_id": "1",
            "custom_canvas_api_domain": config.TESTING_API_URL,
        }

        signed_url = self.generate_launch_request(
            "/launch",
            http_method="POST",
            roles="User",
            body=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        response = self.client.post(signed_url, data=payload)

        self.assert_200(response)
        self.assert_template_used("error.html")
        self.assertIn(b"Not authorized", response.data)

    @patch("config.ALLOWED_CANVAS_DOMAINS", [config.TESTING_API_URL])
    def test_lti_tool(self, m):
        payload = {
            "launch_presentation_return_url": "http://localhost/",
            "custom_canvas_api_domain": config.TESTING_API_URL,
            "custom_canvas_user_id": "1",
            "custom_canvas_course_id": "1",
        }

        signed_url = self.generate_launch_request(
            "/launch",
            http_method="POST",
            body=payload,
            roles="urn:lti:instrole:ims/lis/Administrator",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        response = self.client.post(signed_url, data=payload)

        with self.client.session_transaction() as session:
            self.assertRedirects(response, "/quiz/1/")
            self.assertTrue(session.get("is_admin"))

    def test_lti_tool_bad_domain(self, m):
        payload = {
            "launch_presentation_return_url": "http://localhost/",
            "custom_canvas_api_domain": "example.com",
            "custom_canvas_user_id": "1",
            "custom_canvas_course_id": "1",
        }

        signed_url = self.generate_launch_request(
            "/launch",
            http_method="POST",
            body=payload,
            roles="urn:lti:instrole:ims/lis/Administrator",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        response = self.client.post(signed_url, data=payload,)

        self.assert_template_used("error.html")
        self.assertIn(
            b"This tool is only available from the following domain(s):", response.data,
        )

    @staticmethod
    def generate_launch_request(
        url,
        body=None,
        http_method="GET",
        base_url="http://localhost",
        roles="Instructor",
        headers=None,
    ):
        params = {}

        if roles is not None:
            params["roles"] = roles

        urlparams = urlencode(params)

        client = oauthlib.oauth1.Client(
            "key",
            client_secret="secret",
            signature_method=oauthlib.oauth1.SIGNATURE_HMAC,
            signature_type=oauthlib.oauth1.SIGNATURE_TYPE_QUERY,
        )
        signature = client.sign(
            "{}{}?{}".format(base_url, url, urlparams),
            body=body,
            http_method=http_method,
            headers=headers,
        )
        signed_url = signature[0]
        new_url = signed_url[len(base_url) :]
        return new_url


@requests_mock.Mocker()
class UtilTests(flask_testing.TestCase):
    def create_app(self):
        app = views.app
        app.config["TESTING"] = True
        app.config["DEBUG"] = False
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/test.db"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        app.config["threaded"] = True
        return app

    def setUp(self):
        logging.disable(logging.CRITICAL)
        views.db.init_app(self.app)
        with self.app.test_request_context():
            views.db.create_all()

    def tearDown(self):
        logging.disable(logging.NOTSET)
        views.db.session.remove()
        views.db.drop_all()

    def test_extend_quiz(self, m):
        from utils import extend_quiz

        m.register_uri(
            "POST", "/api/v1/courses/1/quizzes/2/extensions", status_code=200
        )

        response = extend_quiz(
            course_id=1,
            quiz={"id": 2, "title": "A Quiz", "time_limit": 10},
            percent=200,
            user_id_list=[1, 2, 3],
        )
        self.assertIsInstance(response, dict)
        self.assertTrue(response["success"])
        self.assertEqual(
            response["message"], "Successfully added 10 minutes to quiz #2"
        )
        self.assertEqual(response["added_time"], 10)

    def test_extend_quiz_invalid_response(self, m):
        from utils import extend_quiz

        m.register_uri(
            "POST", "/api/v1/courses/1/quizzes/99/extensions", status_code=404
        )

        response = extend_quiz(
            course_id=1,
            quiz={"id": 99, "title": "A Quiz", "time_limit": 10},
            percent=200,
            user_id_list=[1, 2, 3],
        )
        self.assertIsInstance(response, dict)
        self.assertFalse(response["success"])
        self.assertEqual(
            response["message"],
            "Error creating extension for quiz #99. Canvas status code: 404",
        )
        self.assertEqual(response["added_time"], None)

    def test_extend_quiz_no_time_limit(self, m):
        from utils import extend_quiz

        response = extend_quiz(
            course_id=1,
            quiz={"id": 2, "title": "A Quiz"},
            percent=200,
            user_id_list=[1, 2, 3],
        )
        self.assertIsInstance(response, dict)
        self.assertTrue(response["success"])
        self.assertEqual(
            response["message"],
            "Quiz #2 has no time limit, so there is no time to add.",
        )
        self.assertEqual(response["added_time"], None)

    def test_get_quizzes(self, m):
        from utils import get_quizzes

        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json=[{"id": 1, "title": "Quiz 1"}, {"id": 2, "title": "Quiz 2"}],
        )

        response = get_quizzes(1)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 2)

    def test_get_quizzes_error(self, m):
        from utils import get_quizzes

        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json={"errors": {"message": "An error occurred."}},
        )

        response = get_quizzes(1)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 0)

    def test_search_students(self, m):
        from utils import search_students

        m.register_uri(
            "GET",
            "/api/v1/courses/1/search_users",
            json=[{"id": 1, "name": "John Smith"}, {"id": 2, "name": "Jane Doe"}],
            headers={
                "Link": '<http://example.com/api/v1/courses/1/search_users?page=99>; rel="last"'
            },
        )

        response = search_students(1)

        self.assertIsInstance(response, tuple)

        self.assertIsInstance(response[0], list)
        self.assertEqual(len(response[0]), 2)

        self.assertIsInstance(response[1], int)
        self.assertEqual(response[1], 99)

    def test_search_students_malformed_response(self, m):
        from utils import search_students

        m.register_uri("GET", "/api/v1/courses/1/search_users")
        response = search_students(1)

        self.assertIsInstance(response, tuple)

        self.assertIsInstance(response[0], list)
        self.assertEqual(len(response[0]), 0)

        self.assertIsInstance(response[1], int)
        self.assertEqual(response[1], 0)

    def test_search_students_error(self, m):
        from utils import search_students

        m.register_uri(
            "GET",
            "/api/v1/courses/1/search_users",
            json={"errors": {"message": "An error occurred."}},
        )

        response = search_students(1)

        self.assertIsInstance(response, tuple)

        self.assertIsInstance(response[0], list)
        self.assertEqual(len(response[0]), 0)

        self.assertIsInstance(response[1], int)
        self.assertEqual(response[1], 0)

    def test_search_students_no_last_link(self, m):
        from utils import search_students

        m.register_uri(
            "GET",
            "/api/v1/courses/1/search_users",
            json=[{"id": 1, "name": "John Smith"}],
        )

        response = search_students(1)

        self.assertIsInstance(response, tuple)

        self.assertIsInstance(response[0], list)
        self.assertEqual(len(response[0]), 1)

        self.assertIsInstance(response[1], int)
        self.assertEqual(response[1], 0)

    def test_get_user(self, m):
        from utils import get_user

        m.register_uri(
            "GET",
            "/api/v1/courses/1/users/1",
            json={"id": 1, "sortable_name": "John Smith"},
        )

        response = get_user(1, 1)

        self.assertIsInstance(response, dict)
        self.assertEqual(response["sortable_name"], "John Smith")

    def test_get_user_not_found(self, m):
        from utils import get_user

        m.register_uri("GET", "/api/v1/courses/1/users/1", status_code=404)

        with self.assertRaises(requests.exceptions.HTTPError):
            get_user(1, 1)

    def test_get_course(self, m):
        from utils import get_course

        m.register_uri(
            "GET", "/api/v1/courses/1", json={"id": 1, "title": "Example Course"}
        )

        response = get_course(1)

        self.assertIsInstance(response, dict)
        self.assertEqual(response["title"], "Example Course")

    def test_get_course_not_found(self, m):
        from utils import get_course

        m.register_uri("GET", "/api/v1/courses/1", status_code=404)

        with self.assertRaises(requests.exceptions.HTTPError):
            get_course(1)

    def test_get_or_create_created(self, m):
        from utils import get_or_create

        quiz_id = 5
        course_id = 1

        quiz, created = get_or_create(
            views.db.session, Quiz, canvas_id=quiz_id, course_id=course_id
        )
        self.assertTrue(created)
        self.assertIsInstance(quiz, Quiz)
        self.assertEqual(quiz.canvas_id, quiz_id)
        self.assertEqual(quiz.course_id, course_id)

    def test_get_or_create_already_exists(self, m):
        from utils import get_or_create

        quiz_id = 5
        quiz_title = "Final Exam"
        course_id = 1

        prebuilt_quiz = Quiz(canvas_id=quiz_id, course_id=course_id, title=quiz_title)
        views.db.session.add(prebuilt_quiz)
        views.db.session.commit()

        quiz, created = get_or_create(
            views.db.session, Quiz, canvas_id=quiz_id, course_id=course_id
        )
        self.assertFalse(created)
        self.assertIsInstance(quiz, Quiz)
        self.assertEqual(quiz.canvas_id, quiz_id)
        self.assertEqual(quiz.course_id, course_id)
        self.assertEqual(quiz.title, quiz_title)

    def test_missing_and_stale_quizzes(self, m):
        from utils import missing_and_stale_quizzes

        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json=[
                {"id": 1, "title": "Quiz 1"},
                {"id": 2, "title": "Quiz 2"},
                {"id": 3, "title": "Quiz 3"},
            ],
        )

        quiz_obj = Quiz(course_id=1, canvas_id=2, title="Quiz 2")
        views.db.session.add(quiz_obj)
        views.db.session.commit()

        response = missing_and_stale_quizzes(1)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 2)
        self.assertEqual(response[0]["title"], "Quiz 1")
        self.assertEqual(response[1]["title"], "Quiz 3")

    def test_missing_and_stale_quizzes_no_missing(self, m):
        from utils import missing_and_stale_quizzes

        m.register_uri(
            "GET", "/api/v1/courses/1/quizzes", json=[{"id": 1, "title": "Quiz 1"}]
        )

        quiz_obj = Quiz(course_id=1, canvas_id=1, title="Quiz 1")
        views.db.session.add(quiz_obj)
        views.db.session.commit()

        response = missing_and_stale_quizzes(1, quickcheck=True)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 0)

    def test_missing_and_stale_quizzes_updated_time_limit(self, m):
        from utils import missing_and_stale_quizzes

        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json=[
                {"id": 1, "title": "Quiz 1", "time_limit": 60},  # remains 60
                {"id": 2, "title": "Quiz 2", "time_limit": 120},  # updated to 120
            ],
        )

        #
        quiz1 = Quiz(course_id=1, canvas_id=1, title="Quiz 1", time_limit=60)
        views.db.session.add(quiz1)
        quiz2 = Quiz(course_id=2, canvas_id=2, title="Quiz 2", time_limit=60)
        views.db.session.add(quiz2)
        views.db.session.commit()

        response = missing_and_stale_quizzes(1)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["title"], "Quiz 2")
        self.assertEqual(response[0]["time_limit"], 120)

    def test_missing_and_stale_quizzes_quickcheck(self, m):
        from utils import missing_and_stale_quizzes

        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json=[
                {"id": 1, "title": "Quiz 1"},
                {"id": 2, "title": "Quiz 2"},
                {"id": 3, "title": "Quiz 3"},
            ],
        )

        quiz_obj = Quiz(course_id=1, canvas_id=2, title="Quiz 2")
        views.db.session.add(quiz_obj)
        views.db.session.commit()

        response = missing_and_stale_quizzes(1, quickcheck=True)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["title"], "Quiz 1")

    def test_missing_and_stale_quizzes_quickcheck_first_item_exists(self, m):
        from utils import missing_and_stale_quizzes

        m.register_uri(
            "GET",
            "/api/v1/courses/1/quizzes",
            json=[
                {"id": 1, "title": "Quiz 1"},
                {"id": 2, "title": "Quiz 2"},
                {"id": 3, "title": "Quiz 3"},
            ],
        )

        quiz_obj = Quiz(course_id=1, canvas_id=1, title="Quiz 1")
        views.db.session.add(quiz_obj)
        views.db.session.commit()

        response = missing_and_stale_quizzes(1, quickcheck=True)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["title"], "Quiz 2")
