from flask import Flask, render_template, session, request,\
	redirect, url_for
from config import *
from functools import wraps

import requests
import json
import math
from urlparse import parse_qs, urlsplit

#OAuth specific
from ims_lti_py import ToolProvider
from time import time

app = Flask(__name__)
app.secret_key = '***REMOVED***'
app.debug = True

oauth_creds = {'key': 'secret', 'eleven': '11'}

headers = {'Authorization': 'Bearer ' + API_KEY}
json_headers = {'Authorization': 'Bearer ' + API_KEY, 'Content-type': 'application/json'}

DEFAULT_PER_PAGE = 10
MAX_PER_PAGE = 100


def check_valid_user(f):
	@wraps(f)
	def decorated_function(*args, **kwargs):
		if not session.get('lti_logged_in') or not session.get('canvas_user_id'):
			return render_template(
				'error.html',
				message='Not allowed!'
			)
		return f(*args, **kwargs)
	return decorated_function


@app.route("/", methods=['POST', 'GET'])
def index():
	return "Please contact Online@UCF support."


@app.route("/xml/", methods=['POST', 'GET'])
def xml():
	return render_template('lti.xml')


@app.route("/quiz/<course_id>", methods=['POST', 'GET'])
@check_valid_user
def quiz(course_id=None):
	if not course_id:
		return render_template(
			'error.html',
			message='course_id required',
		)

	course_url = "%scourses/%s" % (API_URL, course_id)

	user_list, max_pages = search_users(
		course_url,
		per_page=DEFAULT_PER_PAGE,
		page=1
	)

	if not user_list or max_pages < 1:
		return render_template(
			'error.html',
			message='Unable to load users.',
		)

	return render_template(
		'userselect.html',
		users=user_list,
		course_id=course_id,
		current_page_number=1,
		max_pages=max_pages
	)


@app.route("/update/<course_id>/", methods=['POST'])
@check_valid_user
def update(course_id=None):
	if not course_id:
		return "course_id required"

	course_url = "%scourses/%s" % (API_URL, course_id)

	post_json = request.get_json()

	if not post_json:
		return "invalid request"

	user_ids = post_json.get('user_ids', [])
	percent = post_json.get('percent', None)

	quizzes = get_quizzes(course_url)

	for quiz in quizzes:
		quiz_id = quiz.get('id', None)

		time_limit = quiz.get('time_limit', None)

		if time_limit is None or time_limit < 1:
			# Quiz has no time limit so there is no time to add.
			continue

		added_time = math.ceil(time_limit * ((float(percent)-100) / 100) if percent else 0)

		quiz_extensions = {
			'quiz_extensions': []
		}

		for user_id in user_ids:
			user_extension = {
				'user_id': user_id,
				'extra_time': added_time
			}
			quiz_extensions['quiz_extensions'].append(user_extension)

		response = requests.post(
			"%s/quizzes/%s/extensions" % (course_url, quiz_id),
			data=json.dumps(quiz_extensions),
			headers=json_headers
		)

		if response.status_code != 200:
			return "Something went wrong. Status code %s" % (response.status_code)

	quiz_string = "quizzes have" if quiz > 1 else "quiz has"
	return "Success! %s %s been updated for %s student(s) to have %s%% time." % (len(quizzes), quiz_string, len(user_ids), percent)


@app.route("/filter/<course_id>/", methods=['POST', 'GET'])
@check_valid_user
def filter(course_id=None):
	if not course_id:
		return "course_id required"

	course_url = "%scourses/%s" % (API_URL, course_id)

	query = request.args.get('query', '').lower()
	page = int(request.args.get('page', 1))
	per_page = int(request.args.get('per_page', DEFAULT_PER_PAGE))

	user_list, max_pages = search_users(
		course_url,
		per_page=per_page,
		page=page,
		search_term=query
	)

	if not user_list or max_pages < 1:
		return 'Unable to load users.'

	return render_template(
		'user_list.html',
		users=user_list,
		current_page_number=page,
		max_pages=max_pages
	)


def get_quizzes(course_url, per_page=MAX_PER_PAGE):
	quizzes = []
	quizzes_url = "%s/quizzes?per_page=%d" % (course_url, per_page)

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


def search_users(course_url, per_page=DEFAULT_PER_PAGE, page=1, search_term=""):
	users_url = "%s/search_users?per_page=%s&page=%s" % (
		course_url,
		per_page,
		page
	)

	users_response = requests.get(
		users_url,
		data={'search_term': search_term},
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


@app.route('/launch', methods=['POST'])
def lti_tool():
	course_id = request.form.get('custom_canvas_course_id')
	canvas_user_id = request.form.get('custom_canvas_user_id')

	roles = request.form['ext_roles']
	if not "Administrator" in roles or not "Instructor" in roles:
		return render_template('error.html',
			message='Must be an Administrator or Instructor',
			params=request.form
		)

	key = request.form.get('oauth_consumer_key')
	if key:
		secret = oauth_creds.get(key)
		if secret:
			tool_provider = ToolProvider(key, secret, request.form)
		else:
			tool_provider = ToolProvider(None, None, request.form)
			tool_provider.lti_msg = 'Your consumer didn\'t use a recognized key'
			tool_provider.lti_errorlog = 'You did it wrong!'
			return render_template('error.html',
				message='Consumer key wasn\'t recognized',
				params=request.form)
	else:
		return render_template('error.html', message='No consumer key')

	if not tool_provider.is_valid_request(request):
		return render_template('error.html',
			message='The OAuth signature was invalid',
			params=request.form)

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
		return redirect(url_for('quiz', course_id=course_id, **request.form))


def was_nonce_used_in_last_x_minutes(nonce, minutes):
	return False

if __name__ == "__main__":
	app.debug = True
	app.secret_key = SECRET_KEY
	app.run(host="0.0.0.0", port=8080)
