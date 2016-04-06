from __future__ import unicode_literals
from __future__ import print_function

from ._exposed import exposed_elements
from ..compat import with_metaclass
from .. import errors


class _ViewCallable(object):
    call_with_context = True

    def __init__(self, view_class):
        self.view_class = view_class
        self.__code__ = view_class

    def __call__(self, context, *args, **kwargs):
        view = self.view_class()
        return view(context)


class ViewMeta(type):
    """Auto registers type."""

    def __new__(cls, name, base, attrs):
        view_class = type.__new__(cls, name, base, attrs)
        if name != "View":
            if not view_class.libname and not view_class.name:
                raise errors.StartupFailedError("{!r} requires a 'name' or 'libname' attribute".format(view_class))
            libname = view_class.libname or "view.{}".format(view_class.name)
            exposed_elements[libname] = _ViewCallable(view_class)
        return view_class


class ViewType(object):

    def __init__(self):
        pass

    def __call__(self, context):
        request = context['.request']
        verb = request.method.lower()
        method = getattr(self, verb, None)
        result = method(request)
        return result


class View(with_metaclass(ViewMeta, ViewType)):
    libname = None
    name = None
    content = None
    template = None
