from __future__ import unicode_literals

from .. import errors
from ..tools import extract_namespace
from .. import namespaces
from ..compat import itervalues

from collections import defaultdict
import inspect


class Meta(object):
    logic_skip = False
    virtual_tag = False
    is_call = False
    is_try = False
    is_loop = False
    app_first_arg = False
    text_nodes = None
    trap_exceptions = False
    translate = False


class ElementRegistry(object):

    default_registry = None

    _registry_stack = []

    def clear(self):
        self._registry.clear()
        self._dynamic_elements.clear()
        del self._registry_stack[:]

    @classmethod
    def push_registry(cls, registry):
        cls._registry_stack.append(registry)

    @classmethod
    def pop_registry(cls):
        cls._registry_stack.pop()

    @classmethod
    def get_default(cls):
        return cls._registry_stack[-1]

    def __init__(self, update_from_default=True):
        self._registry = defaultdict(dict)
        self._dynamic_elements = {}

        if update_from_default:
            self._registry.update(self.default_registry._registry)
            self._dynamic_elements.update(self.default_registry._dynamic_elements)

    def clone(self):
        """Return a copy of this registry"""
        registry = ElementRegistry(update_from_default=False)
        registry._registry = self._registry.copy()
        registry._dynamic_elements = self._dynamic_elements.copy()
        return registry

    def set_default(self):
        """Reset this registry to the default registry (before project loaded)"""
        self._registry = self.default_registry._registry.copy()
        self._dynamic_elements = self.default_registry._dynamic_elements.copy()

    def register_element(self, xmlns, name, element):
        """Add a dynamic element to the element registry"""
        xmlns = xmlns or namespaces.run
        if name in self._registry[xmlns]:
            element_class = self._registry[xmlns][name]
            definition = getattr(element_class, '_location', None)
            if definition is None:
                definition = inspect.getfile(element_class)
            if xmlns:
                raise errors.ElementError('<{}> already registered in "{}" for xmlns "{}"'.format(name, definition, xmlns),
                                          element=getattr(element, 'element', element))
            else:
                raise errors.ElementError('<{}/> already registered in "{}"'.format(name, definition),
                                          element=element)

        self._registry[xmlns][name] = element

    def add_dynamic_registry(self, xmlns, element_callable):
        """Add a dynamic registry (element factory)"""
        self._dynamic_elements[xmlns] = element_callable

    def clear_registry(self):
        """Clear the registry (called on archive reload)"""
        self._registry.clear()

    def get_elements_in_xmlns(self, xmlns):
        """Get all elements defined within a given namespace"""
        return self._registry.get(xmlns, {})

    def get_elements_in_lib(self, long_name):
        """Get all elements defined by a given library"""
        lib_elements = []
        for namespace in itervalues(self._registry):
            lib_elements.extend(element for element in itervalues(namespace)
                                if element._lib_long_name == long_name)
        return lib_elements

    def get_element_type(self, xmlns, name):
        """Get an element by namespace and name"""
        if xmlns in self._dynamic_elements:
            return self._dynamic_elements[xmlns](name)
        return self._registry.get(xmlns, {}).get(name, None)

    def find_xmlns(self, name):
        """Find the xmlns with contain a given tag, or return None"""
        for xmlns in sorted(self._registry.keys()):
            if name in self._registry[xmlns]:
                return xmlns
        return None

    def check_namespace(self, xmlns):
        """Check if a namespace exists in the registry"""
        return xmlns in self._registry

    def set_registry(self, registry):
        """Restore a saved registry"""
        self._registry = registry._registry.copy()
        self._dynamic_elements = registry._dynamic_elements.copy()

    def get_tag(self, tag):
        """Get a tag from it's name (in Clarke's notation)"""
        return self.get_element_type(*extract_namespace(tag))

default_registry = ElementRegistry.default_registry = ElementRegistry(update_from_default=False)
ElementRegistry.push_registry(ElementRegistry.default_registry)
