"""
A WSGI application to run a Moya service

"""

from __future__ import unicode_literals
from __future__ import print_function

from moya.multiwsgi import Service

application = Service()
