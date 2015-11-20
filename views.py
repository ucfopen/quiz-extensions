from flask import Flask, render_template, session, request,\
	make_response, redirect, url_for, Response, jsonify
from config import *

from operator import itemgetter
import requests
import json

#OAuth specific
from ims_lti_py import ToolProvider
from time import time

app = Flask(__name__)
app.secret_key = '***REMOVED***'
app.debug = True

oauth_creds = {'key': 'secret', 'eleven': '11'}

course_id = "839732"  # TODO: get this dynamically
headers = {'Authorization': 'Bearer ' + API_KEY}
json_headers = {'Authorization': 'Bearer ' + API_KEY, 'Content-type': 'application/json'}

COURSE_URL = "%scourses/%s" % (API_URL, course_id)


@app.route("/", methods=['POST', 'GET'])
def index():
	msg = "This is the index."
	return render_template('index.html', msg=msg)


@app.route("/xml/", methods=['POST', 'GET'])
def xml():
	return render_template('lti.xml')


@app.route("/quiz/", methods=['POST', 'GET'])
def quiz():
	users = get_enrollment_users()
	return render_template('userselect.html', users=users)


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
			"%s/quizzes/%s/extensions" % (COURSE_URL, quiz_id),
			data=json.dumps(quiz_extensions),
			headers=json_headers
		)

		if response.status_code != 200:
			import ipdb; ipdb.set_trace()
			return "welp"

	return "success!"


@app.route("/filter/", methods=['POST', 'GET'])
def filter():
	query = request.args.get('query', None).lower()
	users = get_enrollment_users()

	users = [user for user in users if query in user['sortable_name'].lower()]

	return render_template('user_list.html', users=users)


def get_quizzes():
	quizzes = requests.get("%s/quizzes" % (COURSE_URL), headers=headers).json()

	return quizzes


def get_enrollment_users():
	try:
		enrollments = requests.get("%s/enrollments" % (COURSE_URL), data={'type': 'StudentEnrollment'}, headers=headers).json()
	except:
		return []
	enrollment_list = [enrollment.get('user') for enrollment in enrollments]
	return sorted(enrollment_list, key=itemgetter('sortable_name'))


@app.route('/launch', methods = ['POST'])
def lti_tool():
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
