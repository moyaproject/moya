from __future__ import unicode_literals
from __future__ import absolute_import

from .registry import ElementRegistry, Meta
from .. import namespaces
from ..compat import iterkeys, itervalues

from itertools import chain
import inspect
import re

# _meta = ['logic_skip',
#          'virtual_tag',
#          'is_call',
#          'is_try',
#          'is_loop',
#          'app_first_arg',
#          'text_nodes',
#          'trap_exceptions',
#          'trans']


class ElementBaseMeta(type):
    default_namespace = namespaces.default

    @classmethod
    def make_tag_name(cls, name, _re_tag_name=re.compile(r"[A-Z]+[a-z]*")):
        """Convert a tag name from CamelCase to lower-case-and-hyphens"""
        def repl(match):
            return "-" + match.group(0)
        return _re_tag_name.sub(repl, name).strip('_-').lower()

    def __new__(cls, name, base, attrs):
        if '_registry' in attrs:
            registry = attrs['_registry']
        else:
            registry = ElementRegistry.get_default()

        register_element = registry.register_element

        new_class = type.__new__(cls, name, base, attrs)
        xmlns = getattr(new_class, 'xmlns', cls.default_namespace)
        tag_name = cls.make_tag_name(getattr(new_class.Meta, 'tag_name', name))
        if not getattr(new_class.Meta, 'dynamic', False):
            register_element(xmlns, tag_name, new_class)
        new_class._tag_name = tag_name
        attributes = new_class._get_tag_attributes()
        new_class._tag_attributes = attributes
        new_class._tag_attributes_set = frozenset(chain(iterkeys(attributes), ('libname', 'docname', 'if')))
        new_class._required_tag_attributes = frozenset(attribute.name for attribute in itervalues(new_class._tag_attributes) if attribute.required)
        new_class._tag_doc = getattr(new_class, '__moya_doc__', new_class.__doc__)

        new_class._definition = inspect.getsourcefile(new_class)

        _meta = new_class._meta = Meta()
        _meta.__dict__.update(new_class.Meta.__dict__)

        return new_class
