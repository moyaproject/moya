from __future__ import unicode_literals
from __future__ import print_function

from .compat import string_types, with_metaclass, iteritems


class ProtocolEnumBase(type):
    """A little syntactical sugar for enum types"""

    def __new__(cls, name, bases, attrs):
        new_cls = type.__new__(cls, name, bases, attrs)
        enum = {}
        reverse_enum = {}

        for k, v in iteritems(attrs):
            if isinstance(v, int) and not k.startswith('_'):
                enum[k] = v
                reverse_enum[v] = k

        new_cls._enum = enum
        new_cls._reverse_enum = reverse_enum

        @classmethod
        def lookup(cls, i, default=None):
            return cls._reverse_enum.get(i, default)

        @classmethod
        def get(cls, name):
            return cls._enum[name]

        new_cls.lookup = lookup
        new_cls.get = get

        new_cls.choices = sorted(reverse_enum.items(), key=lambda i: i[1])

        return new_cls


class EnumType():
    """A Protocol Enum instance can behave like a string or a number"""

    __metaclass__ = ProtocolEnumBase
    choices = None

    def __init__(self, value):
        if isinstance(value, string_types):
            if value.isdigit():
                value = int(value)
            else:
                value = self.get(value)
        self.value = int(value)

    def __str__(self):
        return self.lookup(self.value, '?')

    def __unicode__(self):
        return self.lookup(self.value, '?')

    def __int__(self):
        return self.value

    def __hash__(self):
        return hash(self.value)

    def __eq__(self, other):
        return self.value == int(other)

    def is_valid(self):
        value = self.lookup(self.value, None)
        return value is not None


class Enum(with_metaclass(ProtocolEnumBase, EnumType)):
    pass


if __name__ == "__main__":
    class HobbitsEnum(Enum):
        SAM = 0
        BILBO = 1
        FRODO = 1
    print(HobbitsEnum(0))
    print(HobbitsEnum(1))
