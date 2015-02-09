from __future__ import unicode_literals
from __future__ import print_function

from webob import Response


class MoyaResponse(Response):

    def __repr__(self):
        return "<moyaresponse {}>".format(self.status)
