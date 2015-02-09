from __future__ import unicode_literals, print_function

from .context.missing import is_missing
from .compat import text_type


class MoyaFilterBase(object):

    def __init__(self, value_name="value"):
        self._value_name = value_name
        super(MoyaFilterBase, self).__init__()

    def get_value_name(self):
        return self._value_name

    def __moyabind__(self, app):
        return BoundFilter(app, self)

    def __moyafilter__(self, context, app, value, **params):
        params[self.get_value_name()] = value
        filter_call = self.lib.archive.get_callable(self.element_ref, app=app)
        value = filter_call(context, **params)
        return value

    def __moyacall__(self, params):
        return MoyaFilterParams(self, params)


class BoundFilter(MoyaFilterBase):
    def __init__(self, app, _filter):
        self.app = app
        self._filter = _filter
        super(BoundFilter, self).__init__()

    def get_value_name(self):
        return self._filter.get_value_name()

    def __repr__(self):
        return "{!r} from '{}'".format(self._filter, self.app.name)

    def __moyafilter__(self, context, app, value, **params):
        return self._filter.__moyafilter__(context, self.app, value, **params)


class MoyaFilter(MoyaFilterBase):
    def __init__(self, lib, filter_element, value_name):
        self.lib = lib
        self.element_ref = filter_element
        super(MoyaFilter, self).__init__(value_name)

    def __repr__(self):
        return "<filter '{}'>".format(self.element_ref)


class MoyaFilterExpression(MoyaFilterBase):
    def __init__(self, exp, value_name):
        self.exp = exp
        super(MoyaFilterExpression, self).__init__(value_name)

    def __repr__(self):
        return "<filter '{}'>".format(text_type(self.exp))

    def __moyafilter__(self, context, app, value, **params):
        if is_missing(value):
            return value
        params[self.get_value_name()] = value
        return self.exp(context, **params)

    def __moyacall__(self, params):
        return MoyaFilterParams(self, params)


class MoyaFilterParams(object):
    def __init__(self, filter, params):
        self.filter = filter
        self.params = params

    def __repr__(self):
        return repr(self.filter)

    def __moyafilter__(self, context, app, value, **params):
        if is_missing(value):
            return value
        return self.filter.__moyafilter__(context, app, value, **self.params)
