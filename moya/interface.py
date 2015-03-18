"""Helper classes (mostly mixins) to provide a context interface"""

from __future__ import unicode_literals
from __future__ import print_function


def moya_context_proxy(base_class):
    """Added moyacontext interface to a class"""
    def deco(cls):

        class ContextClass(base_class):
            def __moyacontext__(self, context):
                if not hasattr(self, '_moya_context'):
                    self._moya_context = cls(self)
                return self._moya_context

        ContextClass.__name__ = cls.__name__
        return ContextClass

    return deco


def unproxy(obj):
    """Return the Python interface from a proxy object"""
    if hasattr(obj, '__moyapy__'):
        return obj.__moyapy__()
    return obj


class Proxy(object):

    @property
    def moya_proxy(self):
        if not hasattr(self, '_moya_proxy'):
            self._moya_proxy = self.ProxyInterface(self)
        return self._moya_proxy

    def __moyacontext__(self, context):
        return self.moya_proxy


class AttributeExposer(object):
    """
    Exposes a number of attributes via a dict-like interface

    Attributes to be exposed are contained in a class variable, which should be a sequence
    call `__moya_exposed_attributes__`

    """

    def keys(self):
        return [k.lstrip('_') for k in self.__moya_exposed_attributes__]

    def iterkeys(self):
        return iter(k.lstrip('_') for k in self.__moya_exposed_attributes__)

    def itervalues(self):
        for k in self.__moya_exposed_attributes__:
            yield getattr(self, k)

    def values(self):
        return [getattr(self, k)
                for k in self.__moya_exposed_attributes__]

    def items(self):
        return [(k.lstrip('_'), getattr(self, k))
                for k in self.__moya_exposed_attributes__]

    def iteritems(self):
        for k in self.__moya_exposed_attributes__:
            yield (k.lstrip('_'), getattr(self, k))

    def __getitem__(self, k):
        if k in self.__moya_exposed_attributes__:
            return getattr(self, k)
        if '_' + k in self.__moya_exposed_attributes__:
            return getattr(self, '_' + k)
        raise KeyError(k)

    def __setitem__(self, k, v):
        if k in self.__moya_exposed_attributes__:
            return setattr(self, k, v)
        if '_' + k in self.__moya_exposed_attributes__:
            return setattr(self, '_' + k, v)
        raise KeyError(k)

    def __contains__(self, k):
        return k in self.__moya_exposed_attributes__ or ('_' + k) in self.__moya_exposed_attributes__

    def get(self, k, default=None):
        if k in self.__moya_exposed_attributes__:
            return getattr(self, k, default)
        if '_' + k in self.__moya_exposed_attributes__:
            return getattr(self, '_' + k, default)
        raise KeyError(k)

    def set(self, k, v):
        if k in self.__moya_exposed_attributes__:
            setattr(self, k, v)
        if '_' + k in self.__moya_exposed_attributes__:
            setattr(self, '_' + k, v)
        raise KeyError(k)

    def copy(self):
        return dict(self.iteritems())

    def __iter__(self):
        return iter(k.lstrip('_') for k in self.__moya_exposed_attributes__)

    def __len__(self):
        return len(self.__moya_exposed_attributes__)


class ObjectExposer(AttributeExposer):
    """Exposes non-callable attributes"""

    @property
    def __moya_exposed_attributes__(self):
        if not hasattr(self, '_exposed_attributes'):
            self._exposed_attributes = sorted([k for k in dir(self) if
                                              not k.startswith('_') and not callable(getattr(self, k))])
        return self._exposed_attributes


if __name__ == "__main__":
    class A(AttributeExposer):
        __moya_exposed_attributes__ = ['a', 'b']

        def __init__(self):
            self.a = [1, 2, 3]
            self.foo = 'bar'
            self.b = 99

    a = A()
    print(a.items())
    print('a' in a)
    print('foo' in a)
    print(list(a))
    print(a['a'])
    print(a['b'])
    print(a['foo'])
