import os

# Canvas API URL (e.g. 'http://example.com/api/v1/')
API_URL = os.environ.get("API_URL")
# Canvas API Key
API_KEY = os.environ.get("API_KEY")

# A list of domains that are allowed to use the tool.
# (e.g. ['example.com', 'example.edu'])
ALLOWED_CANVAS_DOMAINS = [os.environ.get("ALLOWED_CANVAS_DOMAINS")]

# The maximum amount of objects the Canvas API will return per page (usually 100)
MAX_PER_PAGE = 100

# A secret key used by Flask for signing. KEEP THIS SECRET!
# (e.g. 'Ro0ibrkb4Z4bZmz1f5g1+/16K19GH/pa')
SECRET_KEY = os.environ.get("SECRET_KEY")

LTI_TOOL_ID = os.environ.get("LTI_TOOL_ID")  # A unique ID for the tool

# URI for database. (e.g. 'mysql://root:root@localhost/quiz_extensions')
SQLALCHEMY_DATABASE_URI = os.environ.get("DB_URI")
SQLALCHEMY_TRACK_MODIFICATIONS = False

GOOGLE_ANALYTICS = os.environ.get("GOOGLE_ANALYTICS")  # The Google Analytics ID to use.

# URL for the redis server (e.g. 'redis://localhost:6379')
REDIS_URL = os.environ.get("REDIS_URL")

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] {%(filename)s:%(lineno)d} %(message)s"
        },
        "bare": {"format": "%(message)s"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "formatter": "standard",
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {"app": {"handlers": ["console"], "level": "DEBUG", "propagate": True}},
}

TESTING_API_URL = "example.edu"  # Used only to run tests


CONSUMER_KEY = os.environ.get("CONSUMER_KEY", "key")
SHARED_SECRET = os.environ.get("SHARED_SECRET", "secret")

# Configuration for LTI
PYLTI_CONFIG = {
    "consumers": {
        CONSUMER_KEY: {"secret": SHARED_SECRET}
        # Feel free to add more key/secret pairs for other consumers.
    },
    "roles": {
        # Maps values sent in the lti launch value of "roles" to a group
        # Allows you to check LTI.is_role('staff') for your user
        "staff": [
            "urn:lti:instrole:ims/lis/Administrator",
            "Instructor",
            # 'ContentDeveloper',
            # 'urn:lti:role:ims/lis/TeachingAssistant'
        ]
    },
}

# Chrome 80 SameSite=None; Secure fix
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "None"
