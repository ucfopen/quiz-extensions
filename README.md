[![Build Status](https://github.com/ucfopen/quiz-extensions/actions/workflows/run-tests.yml/badge.svg)](https://github.com/ucfopen/quiz-extensions/actions/workflows/run-tests.yml/)
[![Coverage Status](https://codecov.io/gh/ucfopen/quiz-extensions/branch/master/graphs/badge.svg?branch=master)](https://codecov.io/gh/ucfopen/quiz-extensions/branch/master/graphs/)
[![Join UCF Open Slack Discussions](https://ucf-open-slackin.herokuapp.com/badge.svg)](https://ucf-open-slackin.herokuapp.com/)

A self-service LTI for faculty to easily extend time for multiple users for
all quizzes at once.

# Table of Contents

- [Installation](#installation)
  - [Development Installation](#development-installation)
  - [Production Installation](#production-installation)
- [Third Party Licenses](#third-party-licenses)

# Installation

## Development Installation

```sh
git clone git@github.com:ucfopen/quiz-extensions.git
```

Switch into the new directory

```sh
cd quiz-extensions
```

Create the config file from the template

```sh
cp config.py.template config.py
```

Fill in the config file

```python
API_URL = ''  # Canvas API URL (e.g. 'http://example.com/api/v1/')
API_KEY = ''  # Canvas API Key

# The default number of objects the Canvas API will return per page (usually 10)
DEFAULT_PER_PAGE = 10
# The maximum amount of objects the Canvas API will return per page (usually 100)
MAX_PER_PAGE = 100

# A secret key used by Flask for signing. KEEP THIS SECRET! (e.g. 'Ro0ibrkb4Z4bZmz1f5g1+/16K19GH/pa')
SECRET_KEY = ''

LTI_KEY = ''  # Consumer Key
LTI_SECRET = ''  # Shared Secret

LTI_TOOL_ID = ''  # A unique ID for the tool

SQLALCHEMY_DATABASE_URI = ''  # URI for database. (e.g. 'mysql://root:root@localhost/quiz_extensions')

GOOGLE_ANALYTICS = ''  # The Google Analytics ID to use.

REDIS_URL = ''  # URL for the redis server (e.g. 'redis://localhost:6379')
```

Create a virtual environment

```sh
virtualenv env
```

Source the environment

```sh
source env/bin/activate
```

Install required packages

- If you want to be able to run tests:

  ```sh
  pip install -r test_requirements.txt
  ```

- Otherwise,

  ```sh
  pip install -r requirements.txt
  ```

Set `FLASK_APP` environment variable

```sh
export FLASK_APP=views.py
```

Migrate database

```sh
flask db upgrade
```

Run the server

```sh
flask run --with-threads
```

Ensure Redis is running. If not, start it with

```sh
redis-server --daemonize yes
```

Ensure RQ Worker is running. If not, start it with

```sh
rq worker quizext
```

## Production Installation

This is for an Ubuntu 16.xx install but should work for other Debian/ubuntu
based installs using Apache and mod_wsgi.

```sh
sudo apt-get update
sudo apt-get install libapache2-mod-wsgi python-dev apache2 python-setuptools python-pip python-virtualenv libxml2-dev libxslt1-dev zlib1g-dev

sudo a2enmod wsgi
sudo service apache2 restart

cd /var/www/

sudo git clone git@github.com:ucfopen/quiz-extensions.git

cd quiz-extensions/

sudo virtualenv env
source env/bin/activate

sudo env/bin/pip install -r requirements.txt

sudo nano /etc/apache2/sites-available/000-default.conf
```

Put this inside 000-default.conf after `VirtualHost *:80` And before the ending `</VirtualHost>`:

```apache
#QUIZ EXTENSION CODE
Alias quiz-ext/static /var/www/quiz-extensions/static
<Directory /var/www/quiz-extensions/static>
    Require all granted
</Directory>

<Directory /var/www/quiz-extensions>
    <Files wsgi.py>
        Require all granted
    </Files>
</Directory>

WSGIDaemonProcess quiz-ext
WSGIProcessGroup quiz-ext
WSGIScriptAlias /quiz-ext /var/www/quiz-extensions/wsgi.py
```

Then:

```sh
sudo service apache2 reload

sudo cp config.py.template config.py

sudo nano config.py
```

Edit your config.py and change the variables to match your server:

```python
DEBUG = False  # Leave False on production

API_URL = ''  # Canvas API URL (e.g. 'http://example.com/api/v1/')
API_KEY = ''  # Canvas API Key

# The default number of objects the Canvas API will return per page (usually 10)
DEFAULT_PER_PAGE = 10
# The maximum amount of objects the Canvas API will return per page (usually 100)
MAX_PER_PAGE = 100

# A secret key used by Flask for signing. KEEP THIS SECRET! (e.g. 'Ro0ibrkb4Z4bZmz1f5g1+/16K19GH/pa')
SECRET_KEY = ''

LTI_KEY = ''  # Consumer Key
LTI_SECRET = ''  # Shared Secret

LTI_TOOL_ID = ''  # A unique ID for the tool
LTI_DOMAIN = ''  # Domain hosting the LTI

SQLALCHEMY_DATABASE_URI = ''  # URI for database. (e.g. 'mysql://root:root@localhost/quiz_extensions')
```

Finally:

```sh
sudo service apache2 reload
```

# Third Party Licenses

This project uses `ims_lti_py` which is [available on GitHub](https://github.com/tophatmonocle/ims_lti_py)
under the MIT license.

## Contact Us

Need help? Have an idea? Just want to say hi? Come join us on the [UCF Open Slack Channel](https://ucf-open-slackin.herokuapp.com) and join the `#quiz-extensions` channel!
