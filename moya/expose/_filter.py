from __future__ import print_function
from __future__ import unicode_literals

from ._exposed import exposed_filters


class PyFilter(object):
    """A Python defined Moya filter."""

    def __init__(self, callable):
        self.callable = callable

    def __repr__(self):
        """Python filter information."""
        return "<pyfilter '{}'>".format(self.callable.func_name)

    def __moyafilter__(self, context, app, value, params):
        """Filter protocol interface."""
        return self.callable(value)


def filter(filtername):
    """Decorator for a filter."""
    def deco(f):
        exposed_filters[filtername] = PyFilter(f)
        return f
    return deco
