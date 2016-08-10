A self-service LTI for faculty to easily extend time for multiple users for all quizzes at once.

Installation
------------

    git clone git@github.com:ucfcdl/quiz-extensions-license.git

Switch into the new directory

    cd quiz-extensions-license

Create the config file from the template

	cp config.py.template config.py

Fill in the config file

	DEBUG = False  # Leave False on production

	HOST = ''  # The IP/URL to run the server on
	PORT = 5000  # The port to run the server on. Must be an integer

	API_URL = ''  # Canvas API URL (e.g. 'http://example.com/api/v1/')
	API_KEY = ''  # Canvas API Key

	SECRET_KEY = ''  # A secret key for signing. KEEP THIS SECRET! (e.g. 'ClU##GM0"glpghx')

	SSL_CONTEXT = None  # Used when configuring SSL on a development server

	LTI_KEY = ''  # Consumer Key
	LTI_SECRET = ''  # Shared Secret

	LTI_TOOL_ID = ''  # A unique ID for the tool
	LTI_DOMAIN = ''  # Domain hosting the LTI
	LTI_LAUNCH_URL = ''  # Launch URL for the LTI, This should match the url for `lti_tool` in views.py (e.g. 'http://example.com/launch')


Create a virtual environment

	virtualenv env

Source the environment

	source env/bin/activate

Install required packages

	pip install -r requirements.txt

Run the server

	python views.py