from __future__ import unicode_literals
from __future__ import print_function

from ..compat import text_type, implements_to_string, implements_bool


def is_missing(obj):
    """Check if an object is missing"""
    return getattr(obj, 'moya_missing', False)


@implements_bool
@implements_to_string
class Missing(object):
    """A value indicating a missing value in the context"""
    moya_missing = True

    def __init__(self, key):
        self.key = text_type(key)

    @classmethod
    def check(cls, obj):
        """Check if an object is missing"""
        # An object is 'missing' if it has an attribute 'moya_missing' set to True
        return getattr(obj, 'moya_missing', False)

    def __moyajson__(self):
        return None

    def __str__(self):
        return ''

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    def __repr__(self):
        return "<missing '%s'>" % self.key

    def __moyaconsole__(self, console):
        console.text("<missing '{}'>".format(self.key), italic=True, bold=True, fg="yellow")

    def __bool__(self):
        return False

    def __getitem__(self, key):
        return self

    def __setitem__(self, key, value):
        raise ValueError("{!r} does not support item assignment".format(self))

    def __iter__(self):
        return iter([])

    def __contains__(self, key):
        return False

    def __len__(self):
        return 0


class MoyaAttributeError(Missing):

    def __init__(self, e):
        self._e = e

    def __repr__(self):
        return "<error ({})>".format(self._e)

    def __moyarepr__(self, context):
        return "<error ({})>".format(self._e)

    def __moyaconsole__(self, console):
        return console.error("<error ({})>".format(self._e))


if __name__ == "__main__":
    m = Missing('foo.bar')
    print(repr(m))
    print(text_type(m))
    print(len(m))
