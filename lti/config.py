import os

# Canvas API URL (e.g. 'http://example.com/api/v1/')
API_URL = os.environ.get("API_URL")

API_KEY = os.environ.get("API_KEY")

DEBUG = int(os.environ.get("DEBUG", 0)) == 1
TESTING = int(os.environ.get("TESTING", 0)) == 1

# A list of domains that are allowed to use the tool.
# (e.g. ['example.com', 'example.edu'])
ALLOWED_CANVAS_DOMAINS = (
    os.environ.get("ALLOWED_CANVAS_DOMAINS", "").replace(" ", "").split(",")
)

PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "https")
# The maximum amount of objects the Canvas API will return per page (usually 100)
MAX_PER_PAGE = int(os.environ.get("MAX_PER_PAGE", 100))

# A secret key used by Flask for signing. KEEP THIS SECRET!
# (e.g. 'Ro0ibrkb4Z4bZmz1f5g1+/16K19GH/pa')
SECRET_KEY = os.environ.get("SECRET_KEY")

# URI for database. (e.g. 'mysql://root:root@localhost/quiz_extensions')
SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI")
SQLALCHEMY_TRACK_MODIFICATIONS = (
    int(os.environ.get("SQLALCHEMY_TRACK_MODIFICATIONS", 0)) == 1
)

GOOGLE_ANALYTICS = os.environ.get(
    "GOOGLE_ANALYTICS", "GA-"
)  # The Google Analytics ID to use.

# URL for the redis server (e.g. 'redis://localhost:6379')
# REDIS_URL = "redis://quiz_redis:6379"
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
        "file": {
            "level": "INFO",
            "formatter": "standard",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/quiz_ext.log",
            "maxBytes": 1024 * 1024 * 5,  # 5 MB
            "backupCount": 5,
        },
    },
    "loggers": {
        "app": {"handlers": ["console", "file"], "level": "DEBUG", "propagate": True}
    },
}

# Used only to run tests
TESTING_API_URL = os.environ.get("TESTING_API_URL")
TESTING_API_KEY = os.environ.get("TESTING_API_KEY")

# Chrome 80 SameSite=None; Secure fix
SESSION_COOKIE_SECURE = int(os.environ.get("SESSION_COOKIE_SECURE", 1)) == 1
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE")
