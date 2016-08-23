A self-service LTI for faculty to easily extend time for multiple users for all quizzes at once.

Development Installation
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
	
Production Installation
------------

This is for an Ubuntu 16.xx install but should work for other Debian/ubuntu based installs using Apache and mod_wsgi

	sudo apt-get update
	sudo apt-get install libapache2-mod-wsgi python-dev apache2 python-setuptools python-pip python-virtualenv libxml2-dev libxslt1-dev zlib1g-dev

	sudo a2enmod wsgi 
	sudo service apache2 restart

	cd /var/www/

	sudo git clone git@github.com:ucfcdl/quiz-extensions-license.git

	cd quiz-extensions-license/

	sudo virtualenv env
	source env/bin/activate

	sudo env/bin/pip install -r requirements.txt 

	sudo nano /etc/apache2/sites-available/000-default.conf
	
Put this inside 000-default.conf after VirtualHost *:80:
        
	#QUIZ EXTENSION CODE
	Alias quiz-ext/static /var/www/quiz-extensions-license/static
	<Directory /var/www/quiz-extensions-license/static>
		Require all granted
	</Directory>
	
	<Directory /var/www/quiz-extensions-license>
		<Files wsgi.py>
		    Require all granted
		</Files>
	</Directory>
	
	
	WSGIDaemonProcess quiz-ext 
	WSGIProcessGroup quiz-ext
	WSGIScriptAlias /quiz-ext /var/www/quiz-extensions-license/wsgi.py

And before the ending </VirtualHost>

Then:

	sudo service apache2 reload

	sudo cp config.py.template config.py

	sudo nano config.py

Edit your config.py and change the variables to match your server:

	DEBUG = False  # Leave False on production
	
	#Not Needed On Production
	HOST = ''  # The IP/URL to run the server on
	PORT = 5000  # The port to run the server on. Must be an integer
	
	API_URL = ''  # Canvas API URL (e.g. 'http://example.com/api/v1/')
	API_KEY = ''  # Canvas API Key
	
	SECRET_KEY = 'SECRET!'  # A secret key for signing. KEEP THIS SECRET! (e.g. 'ClU##GM0"glpghx')
	
	SSL_CONTEXT = None  # Used when configuring SSL on a development server
	
	LTI_KEY = 'key'  # Consumer Key
	LTI_SECRET = 'secret'  # Shared Secret
	
	LTI_TOOL_ID = 'quiz_ext'  # A unique ID for the tool
	LTI_DOMAIN = 'https://url.com/'  # Domain hosting the LTI
	LTI_LAUNCH_URL = 'https://url.com/quiz-ext/launch'  # Launch URL for the LTI, This should match the url for `lti_tool` in views.py 

Finally:
	
	sudo service apache2 reload
	
