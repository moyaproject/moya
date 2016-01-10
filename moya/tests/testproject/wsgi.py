# encoding=UTF-8

# This file serves the project in production
# See http://wsgi.readthedocs.org/en/latest/

from __future__ import unicode_literals
from moya.wsgi import Application

application = Application('./', ['local.ini', 'production.ini'], server='main', logging='prodlogging.ini')
