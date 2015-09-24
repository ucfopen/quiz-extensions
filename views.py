from flask import Flask, render_template, session, request,\
	make_response, redirect, url_for, Response, jsonify
from config import *

#OAuth specific
from ims_lti_py import ToolProvider
from time import time

app = Flask(__name__)
app.secret_key = '***REMOVED***'
app.debug = True

oauth_creds = {'key': 'secret', 'eleven': '11'}


@app.route("/", methods=['POST', 'GET'])
def index():
	msg = "This is the index."
	return render_template('index.html', msg=msg)


@app.route("/xml", methods=['POST', 'GET'])
def xml():
	return render_template('lti.xml')


@app.route("/quiz", methods=['POST', 'GET'])
def quiz():
	return "test"


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
