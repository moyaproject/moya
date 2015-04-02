from __future__ import unicode_literals

from .compat import implements_to_string
from . import diagnose
from .interface import AttributeExposer

__all__ = ["MoyaException",
           "FatalMoyaException",
           "throw"]


@implements_to_string
class MoyaException(Exception, AttributeExposer):
    fatal = False

    __moya_exposed_attributes__ = ["type", "msg", "info", "diagnosis"]

    def __init__(self, type, msg, diagnosis=None, info=None):
        self.type = type
        self.msg = msg
        self._diagnosis = diagnosis
        self.info = info or {}

    @property
    def diagnosis(self):
        return self._diagnosis or diagnose.diagnose_moya_exception(self)

    def __str__(self):
        return '{}: {}'.format(self.type, self.msg)

    def __repr__(self):
        return '<exception %s:"%s">' % (self.type, self.msg)

    def __moyaconsole__(self, console):
        from . import pilot
        console(self.type + ": ", fg="red", bold=True)(self.msg).nl()
        if self.info:
            console.obj(pilot.context, self.info)


class FatalMoyaException(MoyaException):
    fatal = True


def throw(type, msg, diagnosis=None, info=None):
    raise MoyaException(type, msg, diagnosis=diagnosis, info=info)
