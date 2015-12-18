from flask import Flask, render_template, session, request,\
	make_response, redirect, url_for, Response, jsonify
from config import *

from operator import itemgetter
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

course_url = ""  # this is probably a very bad idea to keep as a global.
DEFAULT_PER_PAGE = 10


@app.route("/", methods=['POST', 'GET'])
def index():
	msg = "This is the index."
	return render_template('index.html', msg=msg)


@app.route("/xml/", methods=['POST', 'GET'])
def xml():
	return render_template('lti.xml')


@app.route("/quiz/", methods=['POST', 'GET'])
def quiz():
	enrollments, max_pages = get_enrollments(
		per_page=DEFAULT_PER_PAGE,
		get_all_pages=False
	)
	user_list = [enrollment.get('user') for enrollment in enrollments]
	return render_template(
		'userselect.html',
		users=user_list,
		current_page_number=1,
		max_pages=max_pages
	)


@app.route("/update/", methods=['POST'])
def update():
	post_json = request.get_json()

	if not post_json:
		return "invalid request"

	user_ids = post_json.get('user_ids', [])
	percent = post_json.get('percent', None)

	quizzes = get_quizzes()

	for quiz in quizzes:
		quiz_id = quiz.get('id', None)

		time_limit = quiz.get('time_limit', None)

		if time_limit is None or time_limit == 0:
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
			import ipdb; ipdb.set_trace()
			return "welp"

	return "success!"


@app.route("/filter/", methods=['POST', 'GET'])
def filter():
	query = request.args.get('query', '').lower()
	page = int(request.args.get('page', 1))
	per_page = int(request.args.get('per_page', DEFAULT_PER_PAGE))

	enrollments, max_pages = get_enrollments()
	user_list = [enrollment.get('user') for enrollment in enrollments]

	# if invalid page, default to page 1
	if page < 1 or page > max_pages:
		page = 1

	start_index = (page-1)*per_page
	end_index = page*per_page

	users = [user for user in user_list if query in user['sortable_name'].lower()]
	users_paginated = users[start_index:end_index]

	return render_template(
		'user_list.html',
		users=users_paginated,
		current_page_number=page,
		max_pages=max_pages
	)


def get_quizzes(per_page=100):
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


def get_enrollments(per_page=DEFAULT_PER_PAGE, get_all_pages=True):
	enrollments = []
	enrollment_url = "%s/enrollments?page=1&per_page=%s" % (
		course_url,
		per_page
	)

	while True:
		enrollments_response = requests.get(
			enrollment_url,
			data={'type': 'StudentEnrollment'},
			headers=headers
		)
		enrollments_list = enrollments_response.json()

		if 'errors' in enrollments_list:
			break

		if isinstance(enrollments_list, list):
			enrollments.extend(enrollments_list)
		else:
			enrollments = enrollments_list

		num_pages = int(
			parse_qs(
				urlsplit(
					enrollments_response.links['last']['url']
				).query
			)['page'][0]
		)

		try:
			enrollment_url = enrollments_response.links['next']['url']
		except KeyError:
			break

		if not get_all_pages:
			break

	return enrollments, num_pages


@app.route('/launch', methods = ['POST'])
def lti_tool():
	global course_url

	course_id = request.form.get('custom_canvas_course_id')
	course_url = "%scourses/%s" % (API_URL, course_id)

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
				message = 'Consumer key wasn\'t recognized',
				params = request.form)
	else:
		return render_template('error.html', message = 'No consumer key')

	if not tool_provider.is_valid_request(request):
		return render_template('error.html',
			message = 'The OAuth signature was invalid',
			params = request.form)

	if time() - int(tool_provider.oauth_timestamp) > 60*60:
		return render_template('error.html', message = 'Your request is too old.')

	# This does truly check anything, it's just here to remind you  that real
	# tools should be checking the OAuth nonce
	if was_nonce_used_in_last_x_minutes(tool_provider.oauth_nonce, 60):
		return render_template('error.html', message = 'Why are you reusing the nonce?')

	session['launch_params'] = tool_provider.to_params()
	username = tool_provider.username('Dude')

	if tool_provider.is_outcome_service():
		return render_template('assessment.html', username = username)
	else:
		return redirect(url_for('quiz', **request.form))


def was_nonce_used_in_last_x_minutes(nonce, minutes):
	return False

if __name__ == "__main__":
	app.debug = True
	app.run(host="0.0.0.0", port=8080)
