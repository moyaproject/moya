from __future__ import unicode_literals, print_function

from ..errors import BadValueError
from ..versioning import VersionSpec
from ..context import Expression, TrueExpression, FalseExpression, dataindex
from ..dbexpression import DBExpression
from ..context.expressiontime import TimeSpan
from ..context.color import Color as ExpressionColor
from ..context.tools import to_expression
from ..elements.elementproxy import ElementProxy
from ..http import StatusCode
from ..compat import (implements_to_string,
                      int_types,
                      text_type,
                      string_types,
                      with_metaclass)


__all__ = ["Constant",
           "Text",
           "Number",
           "Integer",
           "Index",
           "ExpressionAttribute",
           "ApplicationAttribute",
           "Reference",
           "TimeSpanAttribute",
           "CommaList"]


valid_types = []


class AttributeTypeMeta(type):
    """Keeps a registry of all AttributeType classes"""
    registry = {}

    def __new__(cls, name, base, attrs):
        new_class = type.__new__(cls, name, base, attrs)
        if name != "AttributeType":
            name = getattr(new_class, 'name', name.lower())
            AttributeTypeMeta.registry[name] = new_class
            valid_types.append(name)
        return new_class


def lookup(name):
    """Return the AttributeType of a given name

    Non-string are passed through, unaltered.

    """
    if not isinstance(name, string_types):
        return name
    try:
        return AttributeTypeMeta.registry[name.lower()]
    except KeyError:
        raise KeyError(name)


@implements_to_string
class AttributeTypeBase(object):
    """Base class for attribute types"""
    translate = False

    def __init__(self, element, attribute_name, text):
        self.attribute_name = attribute_name
        self.element = element
        self.text = text
        if not isinstance(text, string_types):
            self.const = True
        else:
            self.const = '${' not in text
        super(AttributeTypeBase, self).__init__()

    def __call__(self, context):
        if self.const:
            return self.process(self.text)
        return self.process(context.sub(self.text))

    @classmethod
    def check(self, value):
        return None

    @property
    def value(self):
        if not hasattr(self, '_value'):
            self._value = self.process(self.text)
        return self._value

    @classmethod
    def get_type_display(cls):
        return cls.type_display

    @classmethod
    def display(cls, value):
        if isinstance(value, text_type):
            return '"{}"'.format(value)

    def process(self, text):
        return text

    def __str__(self):
        return self.text

    def invalid(self, text):
        raise BadValueError("In attribute '{}': '{}' is not a valid {}".format(self.attribute_name, text, self.get_type_display()))


class AttributeType(with_metaclass(AttributeTypeMeta, AttributeTypeBase)):
    pass


class Constant(AttributeType):
    type_display = "constant"

    def __init__(self, element, attribute_name, value):
        self.element = element
        self.attribute_name = attribute_name
        self.value = value

    def __call__(self, context):
        return self.value

    @classmethod
    def get_type_display(self):
        return text_type(self.value)


class Text(AttributeType):
    type_display = "text"

    def __call__(self, context):
        if self.const:
            return self.text
        return self.process(context.sub(self.text))


class Bytes(AttributeType):
    type_display = "bytes"

    def process(self, text):
        try:
            text = self.text.encode('utf-8')
        except:
            raise BadValueError("must be encodeable as UTF-8")
        return text


class Raw(AttributeType):
    type_display = "raw"

    def __call__(self, context):
        return self.text


class Number(AttributeType):
    type_display = "number"

    def process(self, text):
        try:
            return float(text)
        except ValueError:
            self.invalid(text)

    @classmethod
    def check(cls, value):
        if '${' not in value:
            try:
                float(value)
            except:
                return 'expected a number, not "{}"'.format(value)


class Integer(AttributeType):
    type_display = "integer"

    def process(self, text):
        try:
            return int(float(text))
        except ValueError:
            self.invalid(text)

    @classmethod
    def display(cls, value):
        if isinstance(value, int_types):
            return text_type(value)

    @classmethod
    def check(cls, value):
        if '${' not in value:
            try:
                int(float(value))
            except:
                return 'expected an integer, not "{}"'.format(value)


class Color(AttributeType):
    type_display = "color"

    def __call__(self, context):
        return ExpressionColor.parse(context.sub(self.text))

    @classmethod
    def check(cls, value):
        if '${' not in value:
            try:
                ExpressionColor.parse(value)
            except Exception as e:
                return text_type(e)


class Index(AttributeType):
    type_display = "index"

    def __call__(self, context):
        return context.get_sub(self.text)


class Reference(AttributeType):
    type_display = "reference"

    def __init__(self, element, attribute_name, text):
        super(Reference, self).__init__(element, attribute_name, text)
        self.reference = dataindex.parse(self.text)

    def __call__(self, context):
        return self.reference


class Element(AttributeType):
    type_display = "element"

    def __call__(self, context):
        element_ref = context.sub(self.text)
        app, element = self.element.archive.get_element(element_ref, app=context.get(".app"))
        return ElementProxy(context, app, element)


class ElementRef(AttributeType):
    type_display = "element reference"

    def __call__(self, context):
        return context.sub(self.text)


class ExpressionAttribute(AttributeType):
    type_display = "expression"
    name = "expression"

    def __init__(self, element, attribute_name, text):
        self.element = element
        self.attribute_name = attribute_name
        self.exp = Expression(text)

    def __call__(self, context):
        return self.exp.eval(context)

    @classmethod
    def display(cls, value):
        return to_expression(None, value)

    @classmethod
    def check(self, value):
        try:
            Expression(value).compile()
        except Exception as e:
            return text_type(e)
        else:
            return None


class FunctionAttribute(AttributeType):
    type_display = "function"
    name = "function"

    def __init__(self, element, attribute_name, text):
        self.element = element
        self.attribute_name = attribute_name
        self.exp = Expression(text)

    def __call__(self, context):
        return self.exp.make_function(context)

    @classmethod
    def check(self, value):
        try:
            Expression(value).compile()
        except Exception as e:
            return text_type(e)
        else:
            return None


class ApplicationAttribute(AttributeType):
    type_display = "application reference"
    name = "application"

    def __init__(self, element, attribute_name, text):
        self.element = element
        self.attribute_name = attribute_name
        self.text = text

    def __call__(self, context):
        app_name = context.sub(self.text)
        if app_name == '':
            raise BadValueError("app name must not be an empty string")
        if not app_name:
            return None
        try:
            app = self.element.archive.find_app(app_name)
        except Exception as e:
            raise BadValueError(text_type(e))
        return app


class DBExpressionAttribute(AttributeType):
    type_display = "database expression"
    name = "dbexpression"

    def __init__(self, element, attribute_name, text):
        self.element = element
        self.attribute_name = attribute_name
        self.text = text

    def __call__(self, context):
        text = context.sub(self.text)
        return DBExpression(text) if text else None

    @classmethod
    def check(self, value):
        if '${' not in value:
            try:
                DBExpression(value).compile()
            except Exception as e:
                return text_type(e)
            else:
                return None


class Boolean(ExpressionAttribute):
    type_display = "boolean"
    name = "boolean"

    def __init__(self, element, attribute_name, text):
        self.attribute_name = attribute_name
        self.text = text
        if text in ('yes', 'True'):
            self.exp = TrueExpression()
        elif text in ('no', 'False'):
            self.exp = FalseExpression()
        else:
            self.exp = Expression(text)

    @classmethod
    def display(cls, value):
        if isinstance(value, bool):
            return "yes" if value else "no"

    def __call__(self, context):
        return bool(self.exp.eval(context))

    @classmethod
    def check(self, value):
        try:
            Expression(value).compile()
        except Exception as e:
            return text_type(e)
        else:
            return None


class DictExpression(ExpressionAttribute):
    type_display = "dict expression"
    name = "dict"

    def __init__(self, element, attribute_name, text):
        self.attribute_name = attribute_name
        self.exp = Expression(text)

    def __call__(self, context):
        d = self.exp.eval(context)
        if not (hasattr(d, 'items') and hasattr(d, '__getitem__')):
            raise BadValueError("must be a dictionary or similar type")
        return d

    @classmethod
    def check(self, value):
        try:
            Expression(value).compile()
        except Exception as e:
            return text_type(e)
        else:
            return None


class TimeSpanAttribute(AttributeType):
    type_display = "timespan"
    name = "timespan"

    def process(self, text):
        return TimeSpan(text)

    @classmethod
    def check(self, value):
        if '${' not in value:
            try:
                TimeSpan(value)
            except Exception as e:
                return text_type(e)
            else:
                return None


class CommaList(AttributeType):
    type_display = "comma list"
    name = "commalist"

    def process(self, text):
        if ',' in text:
            return [t.strip() for t in text.split(',')]
        else:
            return [text]


class Namespace(AttributeType):
    type_display = "namespace"
    name = "namespace"


class Templates(AttributeType):
    type_display = "list of template paths"
    name = "templates"

    def __call__(self, context):
        sub = context.sub
        text = self.text
        if ',' in text:
            return [sub(t.strip()) for t in text.split(',')]
        else:
            return [text.strip()]


class Template(AttributeType):
    type_display = "template path"
    name = "template"

    def __call__(self, context):
        text = context.sub(self.text).strip()
        return text


class Version(AttributeType):
    type_display = "version spec"
    name = "version"

    def __call__(self, context):
        text = VersionSpec(self.text)
        return text

    @classmethod
    def check(self, value):
        try:
            VersionSpec(value)
        except Exception as e:
            return text_type(e)
        else:
            return None


class HTTPStatus(AttributeType):
    type_display = "http status code"
    name = "httpstatus"

    def __call__(self, context):
        if self.text.isdigit():
            return int(self.text)
        try:
            status_code = StatusCode(self.text)
        except KeyError:
            raise BadValueError("'{}' is not a valid status code".format(self.text))
        status = int(status_code)
        return status

    @classmethod
    def check(self, value):
        try:
            StatusCode(value)
        except Exception as e:
            return ValueError("'{}' is not a valid status code".format(value))
        else:
            return None

if __name__ == "__main__":

    from moya.context import Context
    c = Context()
    c['foo'] = [1, 2, 3, 4, 5]
    c['fruit'] = ['apples', 'orange', 'pears']

    t = Number("${foo.2}.14")
    print(t.__call__)
    print(repr(t))
    print(t(c))

    i = Index("fruit.${foo.1}")
    print(i(c))
