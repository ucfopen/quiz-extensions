import logging

import fakeredis
import flask_testing
import requests_mock
from canvasapi import Canvas
from flask import Flask, session
from flask_caching import Cache
from rq import Queue, SimpleWorker

import views
from models import Course, Extension, Quiz, User, db

# Tests with the suffix "_new" are for testing New Quiz functionality specifically,
# and are identical to their classic quiz counterparts otherwise.

# class ViewTests: Tests functionality in our Flask views (navigating the LTI page)
# class UtilTests: Tests functionality for our backend utility functions

# View Route Testing

# Test Category Headers (search these)
# [LTI TESTS]
# [HOMEPAGE TESTS]
# [UPDATE BACKGROUND TESTS]
# [REFRESH BACKGROUND TESTS]
# [MISSING AND STALE TESTS]


@requests_mock.Mocker()
class ViewTests(flask_testing.TestCase):
    def create_app(self):
        app = Flask(__name__)
        app.config.from_object("config")
        app.config["TESTING"] = True
        app.config["DEBUG"] = False
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/test.db"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

        views.app = app
        views.db.init_app(app)

        views.canvas = Canvas(app.config["TESTING_API_URL"], "DUMMY")
        views.cache = Cache(app)

        views.init_views(app)

        return app

    def setUp(self):
        # with self.app.test_request_context():
        db.drop_all()
        db.create_all()

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

    """
    Required LTI 1.3 session:

    session["launch_id"] = 12345
    session["roles"] = ["http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"]
    """

    # [LTI TESTS]

    def test_lti_no_session(self, m):
        @views.lti_required(role="staff")
        def test_func():
            pass

        # Should break at testing launch_id
        response = test_func()
        self.assertIn("You must use this tool in an LTI context.", response[0])

    def test_lti_no_roles(self, m):
        session["launch_id"] = 12345

        @views.lti_required(role="staff")
        def test_func():
            pass

        response = test_func()
        self.assertIn("No roles found.", response[0])

    def test_lti_invalid_role(self, m):
        session["launch_id"] = 12345
        session["roles"] = ["http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"]

        @views.lti_required(role="staff")
        def test_func():
            pass

        response = test_func()
        self.assertIn("role to use this tool.", response[0])

    # [HOMEPAGE TESTS]

    def test_index(self, m):
        response = self.client.get("/")
        self.assertIn(response.data, b"Please contact your System Administrator.")

    def test_filter_no_students_found(self, m):
        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "title": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/search_users".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[],
        )

        course_id = 1
        response = self.client.get("/filter/{}/".format(course_id))
        self.assert_200(response)
        self.assert_template_used("user_list.html")
        self.assertEqual(len(list(self.get_context_variable("users"))), 0)

    def test_filter(self, m):
        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "title": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/search_users".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[
                {"id": 1, "name": "John Smith"},
                {"id": 2, "name": "Jane Doe"},
                {"id": 3, "name": "Jane Smyth"},
                {"id": 4, "name": "Jon Doe"},
            ],
            headers={
                "Link": f'<{self.app.config["TESTING_API_URL"]}'
                "courses/1/search_users?page=1&per_page=10>; "
                'rel="current",'
                f'<{self.app.config["TESTING_API_URL"]}'
                "courses/1/search_users?page=1&per_page=10>; "
                'rel="first",'
                f'<{self.app.config["TESTING_API_URL"]}'
                "courses/1/search_users?page=1&per_page=10>; "
                'rel="last",'
            },
        )

        course_id = 1
        response = self.client.get("/filter/{}/".format(course_id))
        self.assert_200(response)
        self.assert_template_used("user_list.html")
        self.assertEqual(len(list(self.get_context_variable("users"))), 4)

    def test_quiz(self, m):
        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        response = self.client.get("/quiz/{}/".format(course_id))

        self.assert_200(response)
        self.assert_template_used("userselect.html")
        self.assertEqual(self.get_context_variable("course_id"), str(course_id))

    # [UPDATE BACKGROUND TESTS]

    def test_update_background_no_json(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        job = self.queue.enqueue_call(func=update_background, args=(course_id, None))
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.return_value()

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(job_result["status_msg"], "Invalid Request")

    def test_update_background_no_course(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            status_code=404,
        )

        job = self.queue.enqueue_call(
            func=update_background,
            args=(course_id, {"percent": "200", "user_ids": ["11", "12"]}),
        )
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.return_value()

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(job_result["status_msg"], "Course not found.")

    def test_update_background_no_percent(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        job = self.queue.enqueue_call(
            func=update_background, args=(course_id, {"user_ids": ["11", "12"]})
        )
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.return_value()

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(job_result["status_msg"], "`percent` field required.")

    def test_update_background_refresh_error(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes".format(self.app.config["TESTING_API_URL"]),
            json=[
                {"id": 4, "title": "Quiz 4", "time_limit": 10},
                {"id": 5, "title": "Quiz 5", "time_limit": 30},
            ],
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/11".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 11,
                "name": "Joe Smyth",
                "sortable_name": "Joe Smyth",
                "sis_user_id": "JSmyth11",
                "enrollments": [
                    {"type": "StudentEnrollment", "enrollment_state": "active"}
                ],
            },
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/12".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 12,
                "name": "Jack Smith",
                "sortable_name": "Jack Smith",
                "sis_user_id": "JSmith12",
                "enrollments": [
                    {"type": "StudentEnrollment", "enrollment_state": "active"}
                ],
            },
        )
        m.register_uri(
            "GET",
            "{}api/v1/users/11/enrollments".format(self.app.config["TESTING_API_URL"]),
            json=[
                {
                    "id": 33,
                    "user_id": 11,
                    "type": "StudentEnrollment",
                    "enrollment_state": "active",
                }
            ],
        )
        m.register_uri(
            "GET",
            "{}api/v1/users/12/enrollments".format(self.app.config["TESTING_API_URL"]),
            json=[
                {
                    "id": 34,
                    "user_id": 12,
                    "type": "StudentEnrollment",
                    "enrollment_state": "active",
                }
            ],
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/4/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=404,
            json={"errors": [{"message": "The specified resource does not exist."}]},
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/5/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=404,
            json={"errors": [{"message": "The specified resource does not exist."}]},
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
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
        job_result = job.return_value()

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(
            job_result["status_msg"],
            "Error creating extension for Classic Quiz #4. Canvas status code: Not Found",
        )

    def test_update_background_no_quizzes(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes".format(self.app.config["TESTING_API_URL"]),
            json=[],
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/11".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 11,
                "name": "Joe Smyth",
                "sortable_name": "Joe Smyth",
                "sis_user_id": "JSmyth11",
            },
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/12".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 12,
                "name": "Jack Smith",
                "sortable_name": "Jack Smith",
                "sis_user_id": "JSmith12",
            },
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
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
        job_result = job.return_value()

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
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes".format(self.app.config["TESTING_API_URL"]),
            json=[
                {"id": 4, "title": "Quiz 4", "time_limit": 10},
                {"id": 5, "title": "Quiz 5", "time_limit": 30},
                {"id": 6, "title": "Quiz 6", "time_limit": None},
                {"id": 7, "title": "Quiz 7", "time_limit": None},
            ],
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/11".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 11,
                "name": "Joe Smyth",
                "sortable_name": "Joe Smyth",
                "sis_user_id": "JSmyth11",
            },
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/12".format(self.app.config["TESTING_API_URL"]),
            status_code=404,
            json={"errors": [{"message": "The specified resource does not exist."}]},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/13".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 13,
                "name": "Jack Smith",
                "sortable_name": "Jack Smith",
                "sis_user_id": "JSmith13",
            },
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/4/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=404,
            json={"errors": [{"message": "The specified resource does not exist."}]},
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/5/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
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
        job_result = job.return_value()

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(
            job_result["status_msg"],
            "Error creating extension for Classic Quiz #4. Canvas status code: Not Found",
        )

    def test_update_background(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes".format(self.app.config["TESTING_API_URL"]),
            json=[
                {"id": 4, "title": "Quiz 4", "time_limit": 10},
                {"id": 5, "title": "Quiz 5", "time_limit": 30},
                {"id": 6, "title": "Quiz 6", "time_limit": None},
                {"id": 7, "title": "Quiz 7", "time_limit": None},
            ],
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/11".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 11,
                "name": "Joe Smyth",
                "sortable_name": "Joe Smyth",
                "sis_user_id": "JSmyth11",
            },
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/12".format(self.app.config["TESTING_API_URL"]),
            status_code=404,
            json={"errors": [{"message": "The specified resource does not exist."}]},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/13".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 13,
                "name": "Jack Smith",
                "sortable_name": "Jack Smith",
                "sis_user_id": "JSmith13",
            },
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/4/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/5/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
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
        job_result = job.return_value()

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

    def test_update_background_new(self, m):
        from views import update_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes".format(self.app.config["TESTING_API_URL"]),
            json=[
                {"id": 4, "title": "Quiz 4", "time_limit": 10},
                {"id": 5, "title": "Quiz 5", "time_limit": 30},
                {"id": 6, "title": "Quiz 6", "time_limit": None},
                {"id": 7, "title": "Quiz 7", "time_limit": None},
            ],
        )

        m.register_uri(
            "POST",
            "{}api/quiz/v1/courses/1/quizzes/8/accommodations".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={
                "message": "Accommodations processed",
                "successful": [{"user_id": 11}, {"user_id": 12}, {"user_id": 13}],
                "failed": [],
            },
        )

        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/11".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 11,
                "name": "Joe Smyth",
                "sortable_name": "Joe Smyth",
                "sis_user_id": "JSmyth11",
            },
        )

        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/12".format(self.app.config["TESTING_API_URL"]),
            status_code=404,
            json={"errors": [{"message": "The specified resource does not exist."}]},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/13".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 13,
                "name": "Jack Smith",
                "sortable_name": "Jack Smith",
                "sis_user_id": "JSmith13",
            },
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/4/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/5/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[
                {
                    "id": 8,
                    "title": "Quiz 8",
                    "quiz_settings": {
                        "session_time_limit_in_seconds": 600,
                        "has_time_limit": True,
                    },
                },
                {
                    "id": 9,
                    "title": "Quiz 9",
                    "quiz_settings": {
                        "session_time_limit_in_seconds": 0,
                        "has_time_limit": False,
                    },
                },
            ],
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
        job_result = job.return_value()

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "complete")
        self.assertFalse(job_result["error"])
        self.assertEqual(job_result["percent"], 100)
        self.assertEqual(
            job_result["status_msg"],
            (
                "Success! 3 quizzes have been updated for 3 student(s) to have "
                "200% time. 3 quizzes have no time limit and were left unchanged."
            ),
        )
        ########

    # [REFRESH BACKGROUND TESTS]

    def test_refresh_background_no_course(self, m):
        from views import refresh_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            status_code=404,
        )

        job = self.queue.enqueue_call(func=refresh_background, args=(course_id,))
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.return_value()

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))
        self.assertEqual(job_result["status"], "failed")
        self.assertEqual(job_result["status_msg"], "Course not found.")
        self.assertEqual(job_result["percent"], 0)
        self.assertTrue(job_result["error"])

    def test_refresh_background_no_missing_and_stale_quizzes(self, m):
        from views import refresh_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes".format(self.app.config["TESTING_API_URL"]),
            json=[{"id": 3, "title": "Quiz 3", "time_limit": None}],
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
        )

        quiz = Quiz(3, course_id)
        views.db.session.add(quiz)
        views.db.session.commit()

        job = self.queue.enqueue_call(func=refresh_background, args=(course_id,))
        self.worker.work(burst=True)

        self.assertTrue(job.is_finished)
        job_result = job.return_value()

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
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        m.register_uri(
            "GET",
            "{}api/v1/courses/{}".format(self.app.config["TESTING_API_URL"], course_id),
            json={"id": course_id, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes".format(self.app.config["TESTING_API_URL"]),
            json=[{"id": 1, "title": "Quiz 1", "time_limit": 10}],
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/1/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=404,
            json={"errors": [{"message": "The specificed resource does not exist."}]},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/12345".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 12345,
                "sortable_name": "John Smith",
                "enrollments": [
                    {"type": "StudentEnrollment", "enrollment_state": "active"}
                ],
            },
        )
        m.register_uri(
            "GET",
            "{}api/v1/users/12345/enrollments".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[
                {
                    "id": 222,
                    "user_id": 12345,
                    "type": "StudentEnrollment",
                    "enrollment_state": "active",
                }
            ],
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
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
        job_result = job.return_value()

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "failed")
        self.assertTrue(job_result["error"])
        self.assertEqual(
            job_result["status_msg"],
            (
                "Some quizzes couldn't be updated. Error creating extension "
                "for Classic Quiz #1. Canvas status code: Not Found"
            ),
        )

    def test_refresh_background_missing_user(self, m):
        from views import refresh_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1
        user_id = 9001

        m.register_uri(
            "GET",
            "{}api/v1/courses/{}".format(self.app.config["TESTING_API_URL"], course_id),
            json={"id": course_id, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/{}/quizzes".format(
                self.app.config["TESTING_API_URL"], course_id
            ),
            json=[
                {"id": 1, "title": "Quiz 1", "time_limit": 10},
                {"id": 2, "title": "Quiz 2", "time_limit": 30},
            ],
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/1/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/2/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )
        m.register_uri(
            "GET",
            "{}api/v1/users/{}/enrollments".format(
                self.app.config["TESTING_API_URL"], user_id
            ),
            status_code=404,
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/{}/users/{}".format(
                self.app.config["TESTING_API_URL"], course_id, user_id
            ),
            status_code=404,
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
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

        job = self.queue.enqueue_call(func=refresh_background, args=(course_id,))
        self.worker.work(burst=True)
        self.assertTrue(job.is_finished)
        self.assertEqual(
            f"{job.return_value()["status_msg"]}",
            "No active extensions were found."
            "<br>Extensions for the following students are inactive:<br>Missing User",
        )

    def test_refresh_background_inactive_user(self, m):
        from views import refresh_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1
        user_id = 9001

        m.register_uri(
            "GET",
            "{}api/v1/courses/{}".format(self.app.config["TESTING_API_URL"], course_id),
            json={"id": course_id, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/{}/quizzes".format(
                self.app.config["TESTING_API_URL"], course_id
            ),
            json=[
                {"id": 1, "title": "Quiz 1", "time_limit": 10},
                {"id": 2, "title": "Quiz 2", "time_limit": 30},
            ],
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/1/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/2/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )
        m.register_uri(
            "GET",
            "{}api/v1/users/{}/enrollments".format(
                self.app.config["TESTING_API_URL"], user_id
            ),
            json=[
                {
                    "id": 222,
                    "user_id": user_id,
                    "type": "StudentEnrollment",
                    "enrollment_state": "inactive",
                }
            ],
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/{}/users/{}".format(
                self.app.config["TESTING_API_URL"], course_id, user_id
            ),
            status_code=200,
            json={
                "id": user_id,
                "sortable_name": "John Smith",
                "enrollments": [
                    {"type": "StudentEnrollment", "enrollment_state": "inactive"}
                ],
            },
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
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

        job = self.queue.enqueue_call(func=refresh_background, args=(course_id,))
        self.worker.work(burst=True)
        self.assertTrue(job.is_finished)
        self.assertEqual(
            f"{job.return_value()["status_msg"]}",
            "No active extensions were found."
            "<br>Extensions for the following students are inactive:<br>Missing User",
        )

    def test_refresh_background_update_success(self, m):
        from views import refresh_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        m.register_uri(
            "GET",
            "{}api/v1/courses/{}".format(self.app.config["TESTING_API_URL"], course_id),
            json={"id": course_id, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes".format(self.app.config["TESTING_API_URL"]),
            json=[
                {"id": 1, "title": "Quiz 1", "time_limit": 10},
                {"id": 2, "title": "Quiz 2", "time_limit": 30},
            ],
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/1/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/2/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )

        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/12345".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 12345,
                "sortable_name": "John Smith",
                "enrollments": [
                    {"type": "StudentEnrollment", "enrollment_state": "active"}
                ],
            },
        )
        m.register_uri(
            "GET",
            "{}api/v1/users/12345/enrollments".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[
                {
                    "id": 222,
                    "user_id": 12345,
                    "type": "StudentEnrollment",
                    "enrollment_state": "active",
                }
            ],
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
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
        job_result = job.return_value()

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "complete")
        self.assertFalse(job_result["error"])
        self.assertEqual(job_result["status_msg"], "2 quizzes have been updated.")
        self.assertEqual(job_result["percent"], 100)

    def test_refresh_background_update_success_new(self, m):
        from views import refresh_background

        with self.client.session_transaction() as sess:
            sess["launch_id"] = 12345
            sess["roles"] = [
                "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
            ]

        course_id = 1

        m.register_uri(
            "GET",
            "{}api/v1/courses/{}".format(self.app.config["TESTING_API_URL"], course_id),
            json={"id": course_id, "name": "Example Course"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes".format(self.app.config["TESTING_API_URL"]),
            json=[
                {"id": 1, "title": "Quiz 1", "time_limit": 10},
                {"id": 2, "title": "Quiz 2", "time_limit": 30},
            ],
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/1/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )
        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/2/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )

        m.register_uri(
            "POST",
            "{}api/quiz/v1/courses/1/quizzes/3/accommodations".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={
                "message": "Accommodations processed",
                "successful": [{"user_id": 12345}],
                "failed": [],
            },
        )

        m.register_uri(
            "GET",
            "{}api/v1/courses/1/users/12345".format(self.app.config["TESTING_API_URL"]),
            json={
                "id": 12345,
                "sortable_name": "John Smith",
                "enrollments": [
                    {"type": "StudentEnrollment", "enrollment_state": "active"}
                ],
            },
        )
        m.register_uri(
            "GET",
            "{}api/v1/users/12345/enrollments".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[
                {
                    "id": 222,
                    "user_id": 12345,
                    "type": "StudentEnrollment",
                    "enrollment_state": "active",
                }
            ],
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[
                {
                    "id": 3,
                    "title": "Quiz 3",
                    "quiz_settings": {
                        "session_time_limit_in_seconds": 600,
                        "has_time_limit": True,
                    },
                }
            ],
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
        job_result = job.return_value()

        meta_keys = ["status", "status_msg", "percent", "error"]
        self.assertTrue(all(key in job_result for key in meta_keys))

        self.assertEqual(job_result["status"], "complete")
        self.assertFalse(job_result["error"])
        self.assertEqual(job_result["status_msg"], "3 quizzes have been updated.")
        self.assertEqual(job_result["percent"], 100)

    # [MISSING AND STALE TESTS]

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
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "title": "Course 1"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[{"id": 1, "title": "Quiz 1"}],
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
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

    def test_missing_and_stale_quizzes_check_true_new(self, m):
        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "title": "Course 1"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[],
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[
                {
                    "id": 1,
                    "title": "Quiz 1",
                    "quiz_settings": {
                        "session_time_limit_in_seconds": 600,
                        "has_time_limit": True,
                    },
                }
            ],
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
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "title": "Course 1"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[{"id": 1, "title": "Quiz 1", "time_limit": 0}],
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
        )

        course_id = 1

        course = Course(canvas_id=course_id, course_name="test")
        views.db.session.add(course)
        views.db.session.commit()

        quiz = Quiz(canvas_id=1, course_id=course_id, time_limit=0)
        views.db.session.add(quiz)

        views.db.session.commit()

        extension = Extension(course_id=course_id, user_id=5, percent=200)
        views.db.session.add(extension)
        views.db.session.commit()

        response = self.client.get("/missing_and_stale_quizzes/{}/".format(course_id))

        self.assert_200(response)
        self.assertEqual(response.data, b"false")

    def test_missing_and_stale_quizzes_check_false_new(self, m):
        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "title": "Course 1"},
        )
        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[],
        )
        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[
                {
                    "id": 1,
                    "title": "Quiz 1",
                    "quiz_settings": {
                        "session_time_limit_in_seconds": 0,
                        "has_time_limit": False,
                    },
                }
            ],
        )

        course_id = 1

        course = Course(canvas_id=course_id, course_name="test")
        views.db.session.add(course)
        views.db.session.commit()

        quiz = Quiz(canvas_id=1, course_id=course_id, time_limit=0)
        views.db.session.add(quiz)

        views.db.session.commit()

        extension = Extension(course_id=course_id, user_id=5, percent=200)
        views.db.session.add(extension)
        views.db.session.commit()

        response = self.client.get("/missing_and_stale_quizzes/{}/".format(course_id))

        self.assert_200(response)
        self.assertEqual(response.data, b"false")


# Utility Function Testing

# Test Category Headers (search these)
# [EXTEND QUIZ TESTS]
# [GET OR CREATE TESTS]
# [MISSING AND STALE TESTS]


@requests_mock.Mocker()
class UtilTests(flask_testing.TestCase):
    def create_app(self):
        app = Flask(__name__)
        app.config.from_object("config")
        app.config["TESTING"] = True
        app.config["DEBUG"] = False
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/test.db"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        app.config["threaded"] = True

        views.app = app
        views.db.init_app(app)

        views.canvas = Canvas(app.config["TESTING_API_URL"], "DUMMY")
        views.cache = Cache(app)

        views.init_views(app)

        return app

    def setUp(self):
        logging.disable(logging.CRITICAL)
        # with self.app.test_request_context():
        db.drop_all()
        db.create_all()

        self.queue = Queue(is_async=False, connection=fakeredis.FakeStrictRedis())
        self.worker = SimpleWorker([self.queue], connection=self.queue.connection)

    def tearDown(self):
        logging.disable(logging.NOTSET)
        views.db.session.remove()
        views.db.drop_all()

    # [EXTEND QUIZ TESTS]

    def test_extend_quiz(self, m):
        from utils import extend_quiz

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/2/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={"quiz_extensions": []},
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
        )

        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes/2".format(self.app.config["TESTING_API_URL"]),
            json={"id": 2, "course_id": 1, "title": "A Quiz", "time_limit": 10},
        )

        response = extend_quiz(
            quiz=views.canvas.get_course(1).get_quiz(2),
            is_new=False,
            percent=200,
            user_id_list=[1, 2, 3],
        )
        self.assertIsInstance(response, dict)
        self.assertTrue(response["success"])
        self.assertEqual(
            response["message"], "Successfully added 10 minutes to Classic Quiz #2"
        )
        self.assertEqual(response["added_time"], 10)

    def test_extend_quiz_invalid_response(self, m):
        from utils import extend_quiz

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
        )

        m.register_uri(
            "POST",
            "{}api/v1/courses/1/quizzes/99/extensions".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=404,
            json={"errors": [{"message": "The specified resource does not exist."}]},
        )

        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes/99".format(self.app.config["TESTING_API_URL"]),
            json={"id": 99, "course_id": 1, "title": "A Quiz", "time_limit": 10},
        )

        response = extend_quiz(
            quiz=views.canvas.get_course(1).get_quiz(99),
            is_new=False,
            percent=200,
            user_id_list=[1, 2, 3],
        )
        self.assertIsInstance(response, dict)
        self.assertFalse(response["success"])
        self.assertEqual(
            response["message"],
            "Error creating extension for Classic Quiz #99. Canvas status code: Not Found",
        )
        self.assertEqual(response["added_time"], None)

    def test_extend_quiz_no_time_limit(self, m):
        from utils import extend_quiz

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
        )

        m.register_uri(
            "GET",
            "{}api/v1/courses/1/quizzes/2".format(self.app.config["TESTING_API_URL"]),
            json={"id": 2, "course_id": 1, "title": "A Quiz", "time_limit": None},
        )

        response = extend_quiz(
            quiz=views.canvas.get_course(1).get_quiz(2),
            is_new=False,
            percent=200,
            user_id_list=[1, 2, 3],
        )
        self.assertIsInstance(response, dict)
        self.assertTrue(response["success"])
        self.assertEqual(
            response["message"],
            "Classic Quiz #2 has no time limit, so there is no time to add.",
        )
        self.assertEqual(response["added_time"], None)

    def test_extend_quiz_new(self, m):
        from utils import extend_quiz

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        m.register_uri(
            "POST",
            "{}api/quiz/v1/courses/1/quizzes/2/accommodations".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=200,
            json={
                "message": "Accommodations processed",
                "successful": [{"user_id": 1}, {"user_id": 2}, {"user_id": 3}],
                "failed": [],
            },
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes/2".format(
                self.app.config["TESTING_API_URL"]
            ),
            json={
                "id": 2,
                "title": "A NEW Quiz",
                "quiz_settings": {
                    "session_time_limit_in_seconds": 600,
                    "has_time_limit": True,
                },
            },
        )

        # This code is in update_background, simulating its New Quiz preprocessing

        new_quiz = views.canvas.get_course(1).get_new_quiz(2)
        settings = new_quiz.__getattribute__("quiz_settings")
        if settings["has_time_limit"]:
            # Divide by 60 because Canvas stores new quiz timers in seconds
            new_quiz.time_limit = settings["session_time_limit_in_seconds"] / 60
        else:
            new_quiz.time_limit = 0

        response = extend_quiz(
            quiz=new_quiz,
            is_new=True,
            percent=200,
            user_id_list=[1, 2, 3],
        )
        self.assertIsInstance(response, dict)
        self.assertTrue(response["success"])
        self.assertEqual(
            response["message"], "Successfully added 10 minutes to New Quiz #2"
        )
        self.assertEqual(response["added_time"], 10)

    def test_extend_quiz_new_invalid_response(self, m):
        from utils import extend_quiz

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        m.register_uri(
            "POST",
            "{}api/quiz/v1/courses/1/quizzes/2/accommodations".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=404,
            json={"errors": [{"message": "The specified resource does not exist."}]},
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes/2".format(
                self.app.config["TESTING_API_URL"]
            ),
            json={
                "id": 2,
                "title": "A NEW Quiz",
                "quiz_settings": {
                    "session_time_limit_in_seconds": 600,
                    "has_time_limit": True,
                },
            },
        )

        # This code is in update_background, simulating its New Quiz preprocessing

        new_quiz = views.canvas.get_course(1).get_new_quiz(2)
        settings = new_quiz.__getattribute__("quiz_settings")
        if settings["has_time_limit"]:
            # Divide by 60 because Canvas stores new quiz timers in seconds
            new_quiz.__setattr__(
                "time_limit", settings["session_time_limit_in_seconds"] / 60
            )
        else:
            new_quiz.__setattr__("time_limit", 0)

        response = extend_quiz(
            quiz=new_quiz,
            is_new=True,
            percent=200,
            user_id_list=[1, 2, 3],
        )
        self.assertIsInstance(response, dict)
        self.assertFalse(response["success"])
        self.assertEqual(
            response["message"],
            "Error creating extension for New Quiz #2. Canvas status code: Not Found",
        )

    def test_extend_quiz_new_no_time_limit(self, m):
        from utils import extend_quiz

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes/2".format(
                self.app.config["TESTING_API_URL"]
            ),
            json={
                "id": 2,
                "title": "A NEW Quiz",
                "quiz_settings": {
                    "session_time_limit_in_seconds": None,
                    "has_time_limit": False,
                },
            },
        )

        # This code is in update_background, simulating its New Quiz preprocessing

        new_quiz = views.canvas.get_course(1).get_new_quiz(2)
        settings = new_quiz.__getattribute__("quiz_settings")
        if settings["has_time_limit"]:
            # Divide by 60 because Canvas stores new quiz timers in seconds
            new_quiz.__setattr__(
                "time_limit", settings["session_time_limit_in_seconds"] / 60
            )
        else:
            new_quiz.__setattr__("time_limit", 0)

        response = extend_quiz(
            quiz=new_quiz,
            is_new=True,
            percent=200,
            user_id_list=[1, 2, 3],
        )
        self.assertIsInstance(response, dict)
        self.assertTrue(response["success"])
        self.assertEqual(
            response["message"],
            "New Quiz #2 has no time limit, so there is no time to add.",
        )

    # [GET OR CREATE TESTS]

    def test_get_or_create_created(self, m):
        from utils import get_or_create

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
        )

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

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
        )

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

    # [MISSING AND STALE TESTS]

    def test_missing_and_stale_quizzes(self, m):
        from utils import missing_and_stale_quizzes

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
        )

        m.register_uri(
            "GET",
            f"{self.app.config["TESTING_API_URL"]}api/v1/courses/1/quizzes",
            json=[
                {"id": 1, "title": "Quiz 1", "time_limit": None},
                {"id": 2, "title": "Quiz 2", "time_limit": None},
                {"id": 3, "title": "Quiz 3", "time_limit": None},
            ],
        )

        quiz_obj = Quiz(course_id=1, canvas_id=2, title="Quiz 2")
        views.db.session.add(quiz_obj)
        views.db.session.commit()

        response = missing_and_stale_quizzes(views.canvas, 1)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 2)
        self.assertEqual(response[0].__getattribute__("title"), "Quiz 1")
        self.assertEqual(response[1].__getattribute__("title"), "Quiz 3")

    def test_missing_and_stale_quizzes_new(self, m):
        from utils import missing_and_stale_quizzes

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        m.register_uri(
            "GET",
            f"{self.app.config["TESTING_API_URL"]}api/v1/courses/1/quizzes",
            json=[],
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            json=[
                {
                    "id": 1,
                    "title": "Quiz 1",
                    "quiz_settings": {
                        "session_time_limit_in_seconds": 0,
                        "has_time_limit": False,
                    },
                },
                {
                    "id": 2,
                    "title": "Quiz 2",
                    "quiz_settings": {
                        "session_time_limit_in_seconds": 0,
                        "has_time_limit": False,
                    },
                },
                {
                    "id": 3,
                    "title": "Quiz 3",
                    "quiz_settings": {
                        "session_time_limit_in_seconds": 0,
                        "has_time_limit": False,
                    },
                },
            ],
        )

        quiz_obj = Quiz(course_id=1, canvas_id=2, title="Quiz 2", time_limit=0)
        views.db.session.add(quiz_obj)
        views.db.session.commit()

        response = missing_and_stale_quizzes(views.canvas, 1)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 2)
        self.assertEqual(response[0].__getattribute__("title"), "Quiz 1")
        self.assertEqual(response[1].__getattribute__("title"), "Quiz 3")

    def test_missing_and_stale_quizzes_no_missing(self, m):
        from utils import missing_and_stale_quizzes

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
        )

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        m.register_uri(
            "GET",
            f"{self.app.config["TESTING_API_URL"]}api/v1/courses/1/quizzes",
            json=[{"id": 1, "title": "Quiz 1", "time_limit": None}],
        )

        quiz_obj = Quiz(course_id=1, canvas_id=1, title="Quiz 1")
        views.db.session.add(quiz_obj)
        views.db.session.commit()

        response = missing_and_stale_quizzes(views.canvas, 1, quickcheck=True)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 0)

    def test_missing_and_stale_quizzes_updated_time_limit(self, m):
        from utils import missing_and_stale_quizzes

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
        )

        m.register_uri(
            "GET",
            f"{self.app.config["TESTING_API_URL"]}api/v1/courses/1/quizzes",
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

        response = missing_and_stale_quizzes(views.canvas, 1)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0].__getattribute__("title"), "Quiz 2")
        self.assertEqual(response[0].__getattribute__("time_limit"), 120)

    def test_missing_and_stale_quizzes_quickcheck(self, m):
        from utils import missing_and_stale_quizzes

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
        )

        m.register_uri(
            "GET",
            f"{self.app.config["TESTING_API_URL"]}api/v1/courses/1/quizzes",
            json=[
                {"id": 1, "title": "Quiz 1", "time_limit": None},
                {"id": 2, "title": "Quiz 2", "time_limit": None},
                {"id": 3, "title": "Quiz 3", "time_limit": None},
            ],
        )

        quiz_obj = Quiz(course_id=1, canvas_id=2, title="Quiz 2")
        views.db.session.add(quiz_obj)
        views.db.session.commit()

        response = missing_and_stale_quizzes(views.canvas, 1, quickcheck=True)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0].__getattribute__("title"), "Quiz 1")

    def test_missing_and_stale_quizzes_quickcheck_first_item_exists(self, m):
        from utils import missing_and_stale_quizzes

        m.register_uri(
            "GET",
            "{}api/v1/courses/1".format(self.app.config["TESTING_API_URL"]),
            json={"id": 1, "name": "Example Course"},
        )

        m.register_uri(
            "GET",
            "{}api/quiz/v1/courses/1/quizzes?per_page=100".format(
                self.app.config["TESTING_API_URL"]
            ),
            status_code=500,
        )

        m.register_uri(
            "GET",
            f"{self.app.config["TESTING_API_URL"]}api/v1/courses/1/quizzes",
            json=[
                {"id": 1, "title": "Quiz 1", "time_limit": None},
                {"id": 2, "title": "Quiz 2", "time_limit": None},
                {"id": 3, "title": "Quiz 3", "time_limit": None},
            ],
        )

        quiz_obj = Quiz(course_id=1, canvas_id=1, title="Quiz 1")
        views.db.session.add(quiz_obj)
        views.db.session.commit()

        response = missing_and_stale_quizzes(views.canvas, 1, quickcheck=True)
        self.assertIsInstance(response, list)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0].__getattribute__("title"), "Quiz 2")
