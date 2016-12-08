from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from ..context.dataindex import makeindex
from ..context.missing import is_missing
from .. import errors
from ..document import Document
from ..elements.elementbasemeta import ElementBaseMeta

from ..context.expression import Expression
from ..elements import attributetypes
from ..elements.elementproxy import ElementProxy
from ..tools import textual_list, format_element_type, nearest_word
from ..containers import OrderedDict
from ..application import Application

from ..compat import (implements_to_string,
                      text_type,
                      string_types,
                      with_metaclass,
                      iteritems,
                      iterkeys)

import inspect
import logging
import weakref
from textwrap import dedent
from collections import deque, namedtuple


Closure = namedtuple("Closure", ["element", "data"])

startup_log = logging.getLogger('moya.startup')


class MoyaAttributeError(Exception):
    pass


class Attribute(object):
    def __init__(self,
                 doc,
                 name=None,
                 map_to=None,
                 type=None,
                 required=False,
                 default=None,
                 example=None,
                 metavar=None,
                 context=True,
                 evaldefault=False,
                 oneof=None,
                 synopsis=None,
                 choices=None,
                 translate=None,
                 missing=True,
                 empty=True,
                 ):
        self.doc = doc
        self.name = name
        self.map_to = map_to or name
        if type is None:
            type = 'text'
        self.type_name = type
        try:
            self.type = attributetypes.lookup(type)
        except KeyError:
            raise MoyaAttributeError("Unable to create an attribute of type '{}'".format(type))
        self.required = required
        self.default = default
        self.example = example
        self.metavar = metavar
        self.context = context
        self.evaldefault = evaldefault
        self.oneof = oneof
        self.synopsis = synopsis
        self._choices = choices
        self.translate = translate or self.type.translate
        self.missing = missing
        self.empty = empty
        self.enum = None
        #if translate is not None:
        #    self.translate = translate

    @property
    def choices(self):
        if callable(self._choices):
            return self._choices()
        return self._choices

    def __getstate__(self):
        state = self.__dict__.copy()
        del state['type']
        return state

    def __setstate__(self, state):
        self.__dict__ = state
        self.type = attributetypes.lookup(self.type_name)

    def __moyaelement__(self):
        return self

    @property
    def type_display(self):
        if hasattr(self.type, 'type_display'):
            return self.type.get_type_display()
        return getattr(self.type, 'name', text_type(self.type.__name__))

    def default_display(self, value):
        # if not isinstance(value, text_type):
        #     return ''
        if self.evaldefault:
            return value
        return self.type.display(value) or ''

    def __repr__(self):
        return 'Attribute(name=%r)' % self.name

    def get_param_info(self):
        param_info = {
            "name": self.name,
            "doc": self.doc,
            "type": self.type_display,
            "required": bool(self.required),
            "default": self.default,
            "default_display": self.default_display(self.default),
            "metavar": self.metavar,
            "choices": self.choices,
            "missing": self.missing,
            "empty": self.empty
        }
        return param_info


class _Parameters(object):
    def __init__(self, attr_values, context, lazy=True):
        self.__attr_values = attr_values
        self.__context = context
        self.__cache = {}
        if not lazy:
            for name in self.__attr_values:
                self.__cache[name] = self.__attr_values[name](self.__context)
            self.__context = None

    def __getattr__(self, name):
        if name not in self.__cache:
            self.__cache[name] = self.__attr_values[name](self.__context)
        return self.__cache[name]

    def __repr__(self):
        return repr(self._get_param_dict())

    def _get_param_dict(self):
        d = {}
        for name in self.__attr_values:
            if name not in self.__cache:
                self.__cache[name] = self.__attr_values[name](self.__context)
            d[name] = self.__cache[name]
        return d

    def keys(self):
        return self.__attr_values.keys()

    def values(self):
        return [self[k] for k in iterkeys(self.__attr_values)]

    def items(self):
        return {k: self[k] for k in self.__attr_values}

    def __iter__(self):
        return iter(self.keys())

    def __getitem__(self, key):
        if key not in self.__cache:
            self.__cache[key] = self.__attr_values[key](self.__context)
        return self.__cache[key]

    def __setitem__(self, key, value):
        raise NotImplementedError

    def __contains__(self, key):
        return key in self.__attr_values

    def __moyaconsole__(self, console):
        console.obj(None, self._get_param_dict())


def _open_tag(tag_name, attrs):
    if attrs:
        a = ' '.join('%s="%s"' % (k, v) for k, v in sorted(attrs.items())).strip()
        return '<%s>' % ' '.join((tag_name, a))
    return '</%s>' % tag_name


def _close_tag(tag_name):
    return '</%s>' % tag_name


def _childless_tag(tag_name, attrs):
    if attrs:
        a = ' '.join('%s="%s"' % (k, v) for k, v in sorted(attrs.items())).strip()
        return '<%s/>' % ' '.join((tag_name, a))
    return '<%s/>' % tag_name


class _Eval(object):
    def __init__(self, code, filename):
        self.code = code
        self.filename = filename
        self.compiled_code = compile(code, filename, 'eval')

    def __call__(self, context):
        return eval(self.compiled_code, dict(context=context))

    def __getstate__(self):
        return self.code, self.filename

    def __setstate__(self, state):
        code, filename = state
        self.code = state
        self.filename = filename
        self.compiled_code = compile(code, filename, 'eval')


def make_eval(s, filename='unknown'):
    """Create a function that evaluates a Python expression"""
    return _Eval(s.strip(), filename)


class ElementType(tuple):
    def __eq__(self, other):
        if isinstance(other, string_types):
            return self[1] == other
        return self == other


class NoDestination(object):

    def __eq__(self, other):
        return isinstance(other, NoDestination)

    def __repr__(self):
        return "<no destination>"
no_destination = NoDestination()


class NoValue(object):

    def __reduce__(self):
        """So pickle doesn't create a new instance on unpickling"""
        return b'no_value'

    def __eq__(self, other):
        return isinstance(other, NoValue)
no_value = NoValue()


class Getter(object):
    def __init__(self, value):
        self.value = value

    def __call__(self, context):
        return self.value


class Translator(object):
    def __init__(self, getter, lib):
        self.getter = getter
        self.lib = weakref.proxy(lib)

    def __call__(self, context):
        value = self.getter(context)
        if isinstance(value, text_type):
            return self.lib.translate(context, value)
        else:
            return value


class ChoicesChecker(object):
    def __init__(self, value_callable, name, element, choices):
        self.name = name
        self.element = element
        self.value_callable = value_callable
        self.choices = choices

    def __call__(self, context):
        value = self.value_callable(context)
        if value is not None and value not in self.choices:
            valid_choices = textual_list(self.choices)
            raise errors.ElementError("attribute '{}' must be {} (not '{}') ".format(self.name, valid_choices, value),
                                      element=self.element)
        return value


class MissingChecker(object):
    def __init__(self, value_callable, name, element):
        self.value_callable = value_callable
        self.name = name
        self.element = element

    def __call__(self, context):
        value = self.value_callable(context)
        if is_missing(value):
            raise errors.ElementError("attribute '{}' must not be missing (it is {})".format(self.name, context.to_expr(value)),
                                      diagnosis="The expression has referenced a value on the context which doesn't exist. Check the expression for typos.",
                                      element=self.element)
        return value


class EmptyChecker(object):
    def __init__(self, value_callable, name, element):
        self.value_callable = value_callable
        self.name = name
        self.element = element

    def __call__(self, context):
        value = self.value_callable(context)
        if not value:
            raise errors.ElementError("attribute '{}' must not be empty or evaluate to false (it is {})".format(self.name, context.to_expr(value)),
                                      diagnosis="Check the expression returns a non-empty result.",
                                      element=self.element)
        return value


@implements_to_string
class ElementBaseType(object):
    __metaclass__ = ElementBaseMeta

    _element_class = "data"
    _lib_long_name = None
    _ignore_skip = False
    element_class = "default"
    xmlns = "http://moyaproject.com"
    preserve_attributes = []

    class Meta:
        logic_skip = False
        virtual_tag = False
        is_call = False
        text_nodes = None
        translate = True

    class Help:
        undocumented = True

    @classmethod
    def _get_tag_attributes(cls):
        attributes = OrderedDict()
        for k in dir(cls):
            v = getattr(cls, k)
            if isinstance(v, Attribute):
                name = v.name or k.lstrip('_')
                v.name = name
                attributes[name] = v
        return attributes

    @classmethod
    def _get_base_attributes(cls):
        attributes = {}
        for el in cls.__mro__[1:]:
            if hasattr(el, '_get_tag_attributes'):
                base_attributes = el._get_tag_attributes()
                base_attributes.update(attributes)
                attributes = base_attributes
                break
        return attributes

    @property
    def document(self):
        return self._document()

    @property
    def lib(self):
        return self._document().lib

    @property
    def priority(self):
        return self.lib.priority

    @classmethod
    def extract_doc_info(cls):
        """Extract information to document this tag"""
        doc = {}
        doc['namespace'] = cls.xmlns
        doc['tag_name'] = cls._tag_name
        doc['doc'] = dedent(cls._tag_doc) if cls._tag_doc else cls._tag_doc
        doc['defined'] = getattr(cls, '_definition', '?')

        if hasattr(cls, 'Help'):
            example = getattr(cls.Help, 'example', None)
            doc['example'] = example
            doc['synopsis'] = getattr(cls.Help, 'synopsis', None)

        base_attributes = cls._get_base_attributes()
        attribs = cls._tag_attributes
        params = {}
        inherited_params = {}

        for name, attrib in base_attributes.items():
            inherited_params[name] = attrib.get_param_info()

        for name, attrib in attribs.items():
            if name not in inherited_params:
                params[name] = attrib.get_param_info()

        doc['params'] = params
        doc['inherited_params'] = inherited_params
        return doc

    @classmethod
    def _get_help(cls, attribute_name, default):
        help = getattr(cls, 'Help', None)
        if help is None:
            return default
        return getattr(help, attribute_name, default)

    @property
    def tag_name(self):
        return self._tag_name

    @property
    def moya_name(self):
        ns = self.xmlns
        if ns.startswith('http://moyaproject.com/'):
            ns = ns[len('http://moyaproject.com/'):]
        return "{{{}}}{}".format(ns, self.tag_name)

    def get_app(self, context, app_attribute='from', check=True):
        app = None
        if self.supports_parameter(app_attribute):
            app = self.get_parameter(context, app_attribute)
        if not app:
            app = context.get('.app', None)
        if isinstance(app, string_types):
            app = self.archive.find_app(app)
        if check:
            if not app:
                raise errors.AppMissingError()
            if not isinstance(app, Application):
                raise errors.AppError("expected an application object here, not {!r}".format(app))
        return app

    # def check_app(self, app):
    #     if not isinstance(app, Application):
    #         self.throw("badvalue.notapp", "'app' is not an application")
    #     return app

    def get_proxy(self, context, app):
        return ElementProxy(context, app, self)

    def get_let_map(self, context, check_missing=False):
        """Gets and evaluates attributes set with the item namespace"""
        if self._let:
            if self._let_exp is None:
                self._let_exp = {k: Expression(v).eval for k, v in self._let.items()}
            let_map = {k: v(context) for k, v in self._let_exp.items()}
            if check_missing:
                for k, v in iteritems(let_map):
                    if getattr(v, 'moya_missing', False):
                        raise errors.ElementError("let:{} must not be missing (it is {!r})".format(k, v))
            return let_map
        else:
            return {}

    def get_let_map_eval(self, context, eval, check_missing=False):
        """Gets and evaluates attributes set with the item namespace, with an alternative eval"""
        if self._let:
            eval = eval or context.eval
            let_map = {k: eval(v) for k, v in self._let.items()}
            if check_missing:
                for k, v in iteritems(let_map):
                    if getattr(v, 'moya_missing', False):
                        raise errors.ElementError("let:{} must not be missing (it is {!r})".format(k, v))
            return let_map
        else:
            return {}

    def get_parameters(self, context, *names):
        if not names:
            return _Parameters(self._attr_values, context)

        def make_param(name, get=self._attr_values.__getitem__):
            try:
                return get(name)(context)
            except errors.BadValueError as e:
                self.throw("bad-value.attribute", "Attribute '{}' -- {}".format(name, text_type(e)))
        return [make_param(n) for n in names]

    def compile_expressions(self):
        """Attempt to compile anything that could be an expression (used by precache)"""
        if getattr(self, '_attrs', None):
            for k, v in self._attrs.items():
                try:
                    Expression.compile_cache(v)
                except:
                    pass
                if '${' in v and '}' in v:
                    Expression.extract(v)
        if getattr(self, '_let', None):
            for k, v in self._let.items():
                try:
                    Expression.compile_cache(v)
                except:
                    pass
        if getattr(self, 'text', None):
            Expression.extract(self.text)

    def get_parameters_nonlazy(self, context):
        return _Parameters(self._attr_values, context, lazy=False)

    def get_parameter(self, context, name):
        return self.get_parameters(context, name)[0]

    def get_parameters_map(self, context, *names):
        if not names:
            raise ValueError("One or more attribute names must be supplied")
        get = self._attr_values.__getitem__
        return {name: get(name)(context) for name in names}

    def get_all_parameters(self, context):
        return {k: v(context) for k, v in self._attr_values.items()}

    def get_all_data_parameters(self, context):
        return {k: v(context) for k, v in self._attr_values.items() if not k.startswith('_')}

    def has_parameter(self, name):
        return name in self._tag_attributes and name not in self._missing

    def has_parameters(self, *names):
        return all(name in self._tag_attributes and name not in self._missing for name in names)

    def supports_parameter(self, name):
        return name in self._tag_attributes

    def auto_build(self, context, text, attrs, translatable_attrs):
        _missing = self._missing = set()
        self._attrs = attrs
        self._translatable_attrs = translatable_attrs

        attrs_keys_set = frozenset(attrs.keys())

        if self._required_tag_attributes and not self._required_tag_attributes.issubset(attrs_keys_set):
            missing = []
            for k in self._required_tag_attributes:
                if k not in attrs:
                    missing.append(k)
            if len(missing) == 1:
                raise errors.ElementError("'%s' is a required attribute" % missing[0], element=self)
            else:
                raise errors.ElementError("%s are required attributes" % ", ".join("'%s'" % m for m in missing), element=self)

        if hasattr(self._meta, 'one_of'):
            for group in self._meta.one_of:
                if not any(name in attrs for name in group):
                    raise errors.ElementError("one of {} is required".format(textual_list(group)), element=self)

        if not getattr(self._meta, 'all_attributes', False) and not self._tag_attributes_set.issuperset(attrs_keys_set):
            unknown_attrs = sorted(attrs_keys_set - self._tag_attributes_set)
            diagnosis = ''
            if len(unknown_attrs) == 1:
                msg = "{} is not a valid attribute on this tag"
                nearest = nearest_word(unknown_attrs[0], self._tag_attributes_set)
                if nearest is not None:
                    diagnosis = "Did you mean '{}'?".format(nearest)
                else:
                    diagnosis = "Valid attributes on this tag are {}".format(textual_list(sorted(self._tag_attributes_set)))
            else:
                msg = "Attributes {} are not valid on this tag"

            diagnosis += '\n\nrun the following for more information:\n\n**$ moya help {}**'.format(self.moya_name)

            raise errors.ElementError(msg.format(textual_list(unknown_attrs, 'and')), element=self, diagnosis=diagnosis)

        self._attr_values = attr_values = {}
        for attribute_name, attribute in self._tag_attributes.items():

            if attribute_name not in attrs:
                _missing.add(attribute_name)
                if attribute.evaldefault and attribute.default is not None:
                    value = attribute.type(self, attribute_name, attribute.default)
                else:
                    value = Getter(attribute.default)
            else:
                value = attribute.type(self, attribute_name, attrs[attribute_name])

            name = attribute.map_to or attribute_name
            if not attribute.context:
                value = value.value
            if attribute.choices:
                value = ChoicesChecker(value, name, self, attribute.choices)
            if not attribute.missing:
                value = MissingChecker(value, name, self)
            if not attribute.empty:
                value = EmptyChecker(value, name, self)
            if attribute_name in self._translatable_attrs:
                value = Translator(value, self.lib)
            setattr(self, name, value)
            attr_values[name] = value

        for k, v in attrs.items():
            if k not in self._tag_attributes:
                self._attributes[k] = v
        self.post_build(context)

    def __init__(self, document, xmlns, tag_name, parent_docid, docid, source_line=None):
        super(ElementBaseType, self).__init__()
        self._tag_attributes = self.__class__._tag_attributes
        self._required_tag_attributes = self.__class__._required_tag_attributes
        self._document = weakref.ref(document)
        self.xmlns = xmlns
        self._tag_name = tag_name
        self._element_type = (xmlns, tag_name)
        self.parent_docid = parent_docid
        self._docid = docid
        self._attributes = OrderedDict()
        self._children = []
        self.source_line = source_line
        self.insert_order = 0
        self._libid = None
        self._location = document.location
        if not hasattr(self.__class__, '_definition'):
            self.__class__._definition = inspect.getsourcefile(self.__class__)
        document.register_element(self)

    def close(self):
        pass

    def run(self, context):
        from moya.logic import DeferNodeContents
        yield DeferNodeContents(self)

    # def dumps(self):
    #     data = {
    #         'xmlns': self.xmlns,
    #         'tag_name': self._tag_name,
    #         'parent_docid': self.parent_docid,
    #         'docid': self._docid,
    #         'source_line': self.source_line,
    #         '_attr_values': self._attr_values,
    #         'libname': self.libname,
    #         '_item_attrs': self._let,
    #         'docname': self.docname,
    #         'text': self.text,
    #         '_location': self._location,
    #         '_attributes': self._attributes,
    #         '_code': self._code,
    #         '_let': self._let,
    #         '_missing': self._missing
    #     }
    #     for k in self.preserve_attributes:
    #         data[k] = getattr(self, k)
    #     data['children'] = [child.dumps() for child in self._children]
    #     return data

    # @classmethod
    # def loads(cls, data, document):
    #     element_type = get_element_type(data['xmlns'],
    #                                     data['tag_name'])
    #     element = element_type(document,
    #                            data['xmlns'],
    #                            data['tag_name'],
    #                            data['parent_docid'],
    #                            data['docid'],
    #                            data['source_line'])
    #     element._attr_values = data['_attr_values']
    #     element.libname = data['libname']
    #     element._let = data['_let']
    #     element.docname = data['docname']
    #     element.text = data['text']
    #     element._location = data['_location']
    #     element._attributes = data['_attributes']
    #     element._code = data['_code']
    #     element._missing = data['_missing']

    #     for k, v in element._attr_values.items():
    #         setattr(element, k, v)

    #     for k in element.preserve_attributes:
    #         setattr(element, k, data[k])

    #     element._children = [cls.loads(child, document)
    #                          for child in data['children']]

    #     if element.docname is not None:
    #         document.register_named_element(element.docname, element)
    #     if document.lib:
    #         document.lib.register_element(element)
    #         document.lib.register_named_element(element.libname, element)
    #     return element

    def __str__(self):
        try:
            attrs = self._attributes.copy()
        except:
            attrs = {}
        return _childless_tag(self._tag_name, attrs)

    __repr__ = __str__

    def __eq__(self, other):
        return self._element_type == other._element_type and self.libid == other.libid

    def __ne__(self, other):
        return not (self._element_type == other._element_type and self.libid == other.libid)

    def get_element(self, name, app=None):
        return self.document.get_element(name, app=app, lib=self.lib)

    def get_app_element(self, name, app=None):
        app, element = self.document.get_element(name, app=app, lib=self.lib)
        if app is None:
            app = self.archive.find_app(element.lib.long_name)
        return app, element

    @property
    def archive(self):
        return self.document.archive

    def __iter__(self):
        return iter(self._children)

    def __reversed__(self):
        return reversed(self._children)

    def is_root(self):
        return self.parent_docid is None

    @property
    def parent(self):
        if self.parent_docid is None:
            return None
        return self.document[self.parent_docid]

    def get_ancestor(self, element_type):
        """Find the first ancestor of a given type"""
        parent = self.parent
        while parent is not None:
            if parent._match_element_type(element_type):
                return parent
            parent = parent.parent
        raise errors.ElementNotFoundError(element_type, msg="{} has no ancestor of type {}".format(self, format_element_type(element_type)))

    @property
    def docid(self):
        return self._docid

    @property
    def libid(self):
        if self._libid is not None:
            return self._libid
        if not hasattr(self, 'libname'):
            return None
        if not self.document.lib:
            return None
        return "%s#%s" % (self.document.lib.long_name or '', self.libname)

    def get_appid(self, app=None):
        if app is None:
            return self.libid
        return "%s#%s" % (app.name or '', self.libname)

    def render_tree(self, indent=0):
        indent_str = '  ' * indent
        attrs = self._attributes.copy()

        if not self._children:
            print(indent_str + _childless_tag(self._tag_name, attrs))
        else:
            print(indent_str + _open_tag(self._tag_name, attrs))
            for child in self._children:
                child.render_tree(indent + 1)
            print(indent_str + _close_tag(self._tag_name))

    def process_attrs(self, attrs, attr_types):
        def asint(name, s):
            if s.isdigit() or s.startswith('-') and s[1:].isdigit():
                return int(s)
            raise errors.AttributeTypeError(self, name, s, 'int')

        def asfloat(name, s):
            try:
                return float(s)
            except:
                raise errors.AttributeTypeError(self, name, s, 'float')
        for k in attrs.keys():
            if k not in attr_types:
                continue
            attr_type = attr_types[k]
            if attr_type in (bool, 'bool'):
                attrs[k] = attrs[k].strip().lower() in ('yes', 'true')
            elif attr_type in (int, 'int'):
                attrs[k] = asint(k, attrs[k])
            elif attr_type in (float, 'float'):
                attrs[k] = asfloat(k, attrs[k])
            else:
                attrs[k] = attr_type(attrs[k])

    def _build(self, context, text, attrs, translatable_attrs):
        if self._meta.text_nodes:
            text = ''
        self._text = self.text = text
        self.auto_build(context, text, attrs, translatable_attrs)

    def _add_child(self, element):
        self._children.append(element)

    def _match_element_type(self, element_type):
        if element_type is None:
            return True
        elif isinstance(element_type, tuple):
            return element_type == self._element_type
        else:
            return self._tag_name == element_type

    def find(self, element_type=None, element_class=None, **attrs):
        # 'fast' path
        if not element_type and not element_class:
            if attrs:
                for child in self._children:
                    for k, v in iteritems(child._attributes):
                        if not (k in attrs and attrs[k] == v):
                            continue
                        yield child
            else:
                for child in self._children:
                    yield child

        # 'slow' path
        else:
            for child in self._children:
                if element_type is not None and not child._match_element_type(element_type):
                    continue
                if element_class is not None and child._element_class != element_class:
                    continue
                if not attrs:
                    yield child
                else:
                    for k, v in iteritems(child._attributes):
                        if not (k in attrs and attrs[k] == v):
                            continue
                        yield child

    def replace(self, element):
        """replace this node with a different element"""
        for i, sibling in enumerate(self.parent._children):
            if sibling is self:
                self.parent._children[i] = element
                element.parent_docid = self.parent_docid

    def children(self, element_type=None, element_class=None, **attrs):
        return self.find(element_type, element_class, **attrs)

    def get_child(self, element_type=None):
        return next(self.find(element_type), None)

    @property
    def has_children(self):
        return bool(self._children)

    def any_children(self, element_type=None, element_class=None, **attrs):
        """Check if there is at least one child that matches"""
        for _child in self.children(element_type, element_class, **attrs):
            return True
        return False

    def get_children(self, element_type=None, element_class=None, **attrs):
        return list(self.find(element_type, element_class, **attrs))

    def find_siblings(self, element_type=None, element_class=None, **attrs):
        parent = self.parent
        if parent is None:
            return
        for child in parent._children:
            if element_type is not None and not child._match_element_type(element_type):
                continue
            if element_class is not None and child._element_class != element_class:
                continue
            if not attrs:
                yield child
            else:
                for k, v in iteritems(child._attributes):
                    if not (k in attrs and attrs[k] == v):
                        continue
                    yield child

    @property
    def siblings(self):
        if self.parent is None:
            return []
        return self.parent._children

    def younger_siblings(self, element_type=None, element_class=None, **attrs):
        iter_siblings = self.find_siblings(element_type, element_class, **attrs)
        while 1:
            if next(iter_siblings) is self:
                break
        while 1:
            yield next(iter_siblings)

    def younger_siblings_of_type(self, element_type):
        """Yield younger siblings that have a given type, directly after this element"""
        iter_siblings = self.find_siblings()
        while 1:
            if next(iter_siblings) is self:
                break
        while 1:
            sibling = next(iter_siblings)
            if sibling._element_type == element_type:
                yield sibling
            else:
                break

    @property
    def older_sibling(self):
        try:
            return self.siblings[self.siblings.index(self) + 1]
        except (ValueError, IndexError):
            return None

    @property
    def younger_sibling(self):
        try:
            return self.siblings[self.siblings.index(self) - 1]
        except (ValueError, IndexError):
            return None

    @property
    def next_sibling(self):
        node = self
        while node is not None:
            next_sibling = self.older_sibling
            if next_sibling is None:
                node = node.parent
            return next_sibling
        return None

    def get(self, element_type=None, element_class=None, **attrs):
        for child in self.find(element_type, element_class, **attrs):
            return child
        raise errors.ElementNotFoundError(text_type(element_type))

    def safe_get(self, element_type=None, element_class=None, **attrs):
        for child in self.find(element_type, element_class, **attrs):
            return child
        return None

    def build(self, text, **attrs):
        pass

    def finalize(self, context):
        pass

    def document_finalize(self, context):
        pass

    def lib_finalize(self, context):
        pass

    def get_all_children(self):
        """Recursively get all children"""
        stack = deque([self])
        extend = stack.extend
        children = []
        add_child = children.append
        pop = stack.popleft
        while stack:
            node = pop()
            add_child(node)
            extend(node._children)
        return children

    def post_build(self, context):
        pass

    def __moyaconsole__(self, console):
        console.xml(text_type(self))

    def throw(self, exc_type, msg, info=None, diagnosis=None, **kwargs):
        """Throw a Moya exception"""
        from moya.logic import MoyaException
        if info is None:
            info = {}
        info.update(kwargs)
        raise MoyaException(exc_type, msg, diagnosis=diagnosis, info=info)

    def get_closure(self, context, element=None, extra=None):
        """Get element with a snapshot of data in the local context scope"""
        if element is None:
            element = self
        data = {k: v for k, v in context.items('') if not k.startswith('_')}
        if extra is not None:
            data.update(extra)
        return Closure(element, data)

    def on_logic_exception(self, callstack, exc_node, logic_exception):
        from moya.logic import render_moya_traceback
        render_moya_traceback(callstack, exc_node, logic_exception)


class ElementBase(with_metaclass(ElementBaseMeta, ElementBaseType)):
    pass


class DynamicElementMixin(object):

    def auto_build(self, context, text, attrs, translatable_attrs):
        self._attrs = attrs

        _missing = self._missing = set()
        self._attr_values = attr_values = {}
        for attribute_name, attribute in self._tag_attributes.items():
            if attribute_name not in attrs:
                _missing.add(attribute_name)
                if attribute.evaldefault and attribute.default is not None:
                    value = attribute.type(self, attribute.default)
                else:
                    value = Getter(attribute.default)
            else:
                value = attribute.type(self, attrs[attribute_name])

            name = attribute.map_to or attribute_name
            if not attribute.context:
                value = value.value
            if attribute.choices:
                value = ChoicesChecker(value, name, self, attribute.choices)
            setattr(self, name, value)
            attr_values[name] = value

            if name in translatable_attrs:
                value.translate = True

        for k, v in attrs.items():
            if k not in self._tag_attributes:
                self._attributes[k] = v
        self.post_build(context)


class RenderableElement(ElementBase):
    xmlns = "http://moyaproject.com"


@implements_to_string
class FunctionCallParams(object):
    """Stores parameters for a function call"""
    def __init__(self, *args, **kwargs):
        self._args = list(args)
        self._kwargs = dict(kwargs)
        super(FunctionCallParams, self).__init__()

    def __str__(self):
        args_str = ', '.join(repr(a) for a in self._args)
        kwargs_str = ', '.join('%s=%r' % (k.encode('ascii', 'replace'), repr(v))
                               for k, v in self._kwargs.items())
        return '(%s)' % ', '.join((args_str.strip(), kwargs_str.strip()))

    def __repr__(self):
        return 'FunctionCallParams%s' % text_type(self)

    def append(self, value):
        self._args.append(value)

    def __len__(self):
        return len(self._args)

    def __setitem__(self, key, value):
        if key is None:
            self._args.append(value)
        else:
            if isinstance(key, string_types):
                self._kwargs[key] = value
            else:
                self._args[key] = value

    def __getitem__(self, key):
        if isinstance(key, string_types):
            return self._kwargs[key]
        else:
            return self._args[key]

    def update(self, map):
        self._kwargs.update(map)

    def __contains__(self, key):
        if isinstance(key, string_types):
            return key in self._kwargs
        try:
            self._args[key]
        except IndexError:
            return False
        return True

    def get(self, key, default=None):
        try:
            if isinstance(key, string_types):
                return self._kwargs[key]
            else:
                return self._args[key]

        except (KeyError, IndexError):
            return default

    def get_value(self, key):
        return self._kwargs[key]

    def get_call_params(self):
        return self._args, self._kwargs

    def keys(self):
        return self._kwargs.keys()


_no_return = object()


@implements_to_string
class ReturnContainer(object):
    """A container that stores a single return value"""
    # This has the interface of a dict, but only stores the last value

    def __init__(self, value=None):
        self._key = 'return'
        self._value = value
        super(ReturnContainer, self).__init__()

    def get_return_value(self):
        return self._value

    def __moyarepr__(self, context):
        return "<return {}>".format(self.get_return_value())

    def __setitem__(self, k, v):
        self._key = k
        self._value = v

    def __getitem__(self, k):
        if k == self._key:
            return self._value
        raise KeyError(k)

    def keys(self):
        return [self._key]

    def values(self):
        return [self._value]

    def items(self):
        return [(self._key, self._value)]

    def __iter__(self):
        return iter([self._value])

    def __len__(self):
        return 1

    def append(self, value):
        self._key = 0
        self._value = value

    def update(self, value):
        self._value = value


class CallStackEntry(dict):
    def __init__(self, element, app, yield_element=None, yield_frame=None):
        self.element = element
        self.app = app
        self.yield_element = yield_element
        self.yield_frame = yield_frame
        super(CallStackEntry, self).__init__()


class _CallContext(object):
    def __init__(self, logic_element, context, app, params):
        self.logic_element = logic_element
        self.context = context
        self.app = app
        self.params = params
        self.has_return = False
        self.return_value = None
        self.error = None

    def __enter__(self):
        self._call = self.logic_element.push_call(self.context, self.params, app=self.app)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        call = self.logic_element.pop_call(self.context)
        if exc_type:
            self.error = (exc_type, exc_val, exc_tb)
        else:
            if '_return' in call:
                self.has_return = True
                return_value = call.get('_return')
                if hasattr(return_value, 'get_return_value'):
                    return_value = return_value.get_return_value()
                self.return_value = return_value


class _DeferContext(object):
    def __init__(self, logic_element, context, app):
        self.logic_element = logic_element
        self.context = context
        self.app = app

    def __enter__(self):
        self.logic_element.push_defer(self.context,
                                      app=self.app)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logic_element.pop_defer(self.context)


class LogicElement(ElementBase):
    _element_class = "logic"

    _if = Attribute("Conditional expression", type="expression", map_to="_if", default=True)

    class Meta:
        is_loop = False
        is_try = False

    def check(self, context):
        return self._if(context)

    def logic(self, context):
        yield iter(self.children(element_class="logic"))

    def finalize_logic(self, context, error, **result):
        pass

    def call(self, context, app, **params):
        return _CallContext(self, context, app, params)

    def closure_call(self, context, app, closure_data, **params):
        call_params = closure_data.copy()
        call_params.update(params)
        return _CallContext(self, context, app, call_params)

    def push_call(self, context, params, app=None, yield_element=None, yield_frame=None):
        callstack = context.set_new_call('._callstack', list)
        call = CallStackEntry(self, app, yield_element=yield_element, yield_frame=yield_frame)
        call.update(params)
        callstack.append(call)
        context.root['call'] = call
        context.push_frame('.call')
        return call

    def pop_call(self, context):
        callstack = context.set_new_call('._callstack', list)
        call = callstack.pop()
        context.pop_frame()
        if callstack:
            context.root['call'] = callstack[-1]
        else:
            del context['.call']
        return call

    def defer(self, context, app=None):
        return _DeferContext(self, context, app)

    def push_defer(self, context, app=None):
        callstack = context.set_new_call('._callstack', list)
        call = CallStackEntry(self, app)
        callstack.append(call)
        context.root['call'] = call
        return call

    def pop_defer(self, context):
        callstack = context.set_new_call('._callstack', list)
        call = callstack.pop()
        if callstack:
            context.root['call'] = callstack[-1]
        else:
            del context.root['.call']
        return call

    def push_funccall(self, context):
        funccalls = context.set_new_call('._funccalls', list)
        params = FunctionCallParams()
        funccalls.append(params)
        context.push_scope(makeindex("._funccalls", len(funccalls) - 1))
        return params

    def pop_funccall(self, context):
        funccalls = context['._funccalls']
        context.pop_scope()
        params = funccalls.pop()
        return params


if __name__ == "__main__":

    class TestElement(RenderableElement):

        def build(self, text, p=5, w=11):
            print(p, w)

    document = Document()
    t = TestElement(document, None, 'tag', None, 'foo')
    ElementBase._build(t, '', dict(apples=1))

    t2 = TestElement(document, None, 'tag2', 'foo', 'bar')
    ElementBase._build(t2, '', dict(p=1))

    t3 = TestElement(document, None, 'tag2', 'foo', 'baz')
    ElementBase._build(t3, '', dict(p=2))

    print(ElementBaseMeta.element_namespaces)
    print(t.render_tree())
