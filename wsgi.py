activate_this = '/var/www/quiz-extensions-license/env/bin/activate_this.py'
execfile(activate_this, dict(__file__=activate_this))
import sys
sys.path.insert(0,"/var/www/quiz-extensions-license/")

from views import app as application
