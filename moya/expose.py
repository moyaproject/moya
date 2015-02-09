from __future__ import unicode_literals, print_function, absolute_import

exposed_elements = {}
exposed_filters = {}


def macro(libname):
    def deco(f):
        exposed_elements[libname] = f
        return f
    return deco


class PyFilter(object):

    def __init__(self, callable):
        self.callable = callable

    def __repr__(self):
        return "<pyfilter '{}'>".format(self.callable.func_name)

    def __moyafilter__(self, context, app, value, **params):
        return self.callable(value)


def filter(filtername):
    def deco(f):
        exposed_filters[filtername] = PyFilter(f)
        return f
    return deco
