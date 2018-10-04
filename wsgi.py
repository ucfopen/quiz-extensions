from views import app as application
import sys

activate_this = '/var/www/quiz-extensions/env/bin/activate_this.py'
execfile(activate_this, dict(__file__=activate_this))
sys.path.insert(0, "/var/www/quiz-extensions/")
