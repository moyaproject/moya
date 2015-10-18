from __future__ import unicode_literals, print_function

from .context.missing import is_missing
from .compat import text_type


class MoyaFilterBase(object):

    def __init__(self, value_name="value", allow_missing=False):
        self._value_name = value_name
        self.allow_missing = allow_missing
        super(MoyaFilterBase, self).__init__()

    def get_value_name(self):
        return self._value_name

    def __moyabind__(self, app):
        return BoundFilter(app, self)

    def __moyafilter__(self, context, app, value, params):
        if not self.allow_missing and is_missing(value):
            raise ValueError("{} doesn't accept a missing value (left hand side is {!r})".format(self, value))

        params[self.get_value_name()] = value
        filter_call = self.lib.archive.get_callable(self.element_ref, app=app)
        value = filter_call(context, **params)
        return value

    def __moyacall__(self, params):
        return MoyaFilterParams(self, params)


class BoundFilter(MoyaFilterBase):
    def __init__(self, _app, _filter):
        self._app = _app
        self._filter = _filter
        self.validator = _filter.validator
        super(BoundFilter, self).__init__()

    def get_value_name(self):
        return self._filter.get_value_name()

    def __repr__(self):
        return "{!r} (app is '{}')".format(self._filter, self._app.name)

    def __moyafilter__(self, context, app, value, params):
        params['_caller_app'] = app
        if self.validator is not None:
            self.validator.check(context, params, self)
        return self._filter.__moyafilter__(context, self._app, value, params)


class MoyaFilter(MoyaFilterBase):
    def __init__(self, lib, filter_element, value_name, allow_missing=False, validator=None):
        self.lib = lib
        self.element_ref = filter_element
        self.validator = validator
        super(MoyaFilter, self).__init__(value_name, allow_missing=allow_missing)

    def __repr__(self):
        return "<filter '{}'>".format(self.element_ref)


class MoyaFilterExpression(MoyaFilterBase):
    def __init__(self, exp, value_name, allow_missing=False):
        self.exp = exp
        super(MoyaFilterExpression, self).__init__(value_name, allow_missing=allow_missing)

    def __repr__(self):
        return "<filter '{}'>".format(text_type(self.exp))

    def __moyafilter__(self, context, app, value, params):
        if is_missing(value):
            return value
        params[self.get_value_name()] = value
        return self.exp(context, params)

    def __moyacall__(self, params):
        return MoyaFilterParams(self, params)


class MoyaFilterParams(object):
    def __init__(self, filter, params):
        self.filter = filter
        self.params = params

    def __repr__(self):
        return repr(self.filter)

    def __moyafilter__(self, context, app, value, params):
        #if self.filter.validator is not None:
        #    self.filter.validator.check(context, params)
        return self.filter.__moyafilter__(context, app, value, self.params)
