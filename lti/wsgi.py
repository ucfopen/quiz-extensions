import sys

from views import app as application
from virtualenv import activation

activate_this = f"{activation.python.__path__[0]}/activate_this.py"
exec(open(activate_this).read(), dict(__file__=activate_this))
sys.path.insert(0, "/var/www/quiz-extensions/")
