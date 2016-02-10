from __future__ import unicode_literals
from __future__ import print_function

from .compat import implements_to_string, string_types, text_type


@implements_to_string
class ContextEnumValue(object):
    """A single value in an enumeration"""

    def __init__(self, enum, enum_id, name, description, group=None):
        self.enum = enum
        self.id = enum_id
        self.name = name
        self.description = description
        self.group = group

    def __repr__(self):
        return "<enumvalue {}.{} ({})>".format(self.enum.name,
                                               self.name,
                                               self.id)

    def __hash__(self):
        return hash((self.id, self.name))

    def __int__(self):
        return self.id

    def __str__(self):
        return self.name

    def __moyadbobject__(self):
        return self.id

    def __moyaconsole__(self, console):
        console("<enumvalue '{}.{}' ({}))>".format(self.enum.name,
                                                   self.name,
                                                   self.id), bold=True, fg="magenta").nl()

    def __eq__(self, other):
        # Other enum values only compare if they are the same type
        if isinstance(other, ContextEnumValue):
            return self.enum == other.enum and self.id == other.id
        if isinstance(other, string_types):
            return self.name == other
        try:
            return self.id == int(other)
        except ValueError:
            pass
        return False


class ContextEnum(object):

    def __init__(self, name, start=1):
        self.name = name
        self._values = []
        self._label_map = {}
        self._id_map = {}
        self._last_id = start - 1

    def __repr__(self):
        return '<enum "{}">'.format(self.name)

    def __moyaconsole__(self, console):
        console.text(repr(self), fg="green", bold=True)
        table = []
        for value in sorted(self._values, key=int):
            table.append([value.name, value.id, value.description or ''])
        console.table(table, header_row=("name", "id", "description"))

    def __eq__(self, other):
        if isinstance(other, ContextEnum):
            return self.name == other.name
        return False

    def add_value(self, name, enum_id=None, description=None, group=None):
        if enum_id is None:
            enum_id = self._last_id + 1
        value = ContextEnumValue(self, enum_id, name, description, group=group)
        self._values.append(value)
        self._label_map[value.name] = value
        self._id_map[value.id] = value
        self._last_id = enum_id
        return value

    def __getitem__(self, key):
        enum_value = None
        if isinstance(key, string_types):
            enum_value = self._label_map[key]
        else:
            try:
                enum_id = int(key)
            except:
                pass
            else:
                enum_value = self._id_map[enum_id]
        if enum_value is None:
            raise KeyError("no enum value {!r} in {!r}".format(key, self))
        return enum_value

    def __contains__(self, key):
        try:
            self[key]
        except:
            return False
        else:
            return True

    def __iter__(self):
        return iter(self._values[:])

    @property
    def choices(self):
        return [(e.name, e.description or e.name) for e in self]

    @property
    def intchoices(self):
        return [(e.id, e.description or e.name) for e in self]

    def keys(self):
        return [int(value) for value in self._values] + [text_type(value) for value in self._values]

    def values(self):
        return [self[key] for key in self.keys()]

    def items(self):
        return [(key, self[key]) for key in self.keys()]


if __name__ == "__main__":

    enum = ContextEnum("moya.admin#enum.hobbits")
    enum.add_value("bilbo", description="Bilbo Baggins")
    enum.add_value("sam", description="Sam")
    enum.add_value("isembard", description="Isembard Took")

    from moya.console import Console
    console = Console()
    console.obj(context, enum)

    e = enum['sam']
    console.obj(context, e)
    print(e)
    print(int(e))
    print(text_type(e))
    print(enum.values())
    print(list(enum))
    print(e == 2)
    print(e == 'sam')
    print(e == 'bilbo')
    print(e == 3)

    print(list(enum))
