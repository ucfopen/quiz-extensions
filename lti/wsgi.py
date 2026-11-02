import sys

from virtualenv import activation

from views import app as application

activate_this = f"{activation.python.__path__[0]}/activate_this.py"
exec(open(activate_this).read(), dict(__file__=activate_this))
sys.path.insert(0, "/var/www/quiz-extensions/")
