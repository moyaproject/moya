from __future__ import unicode_literals
from __future__ import print_function

from ..compat import text_type, number_types, iteritems
from ..context.missing import MoyaAttributeError

import re
import time


def obj_index(obj, key):
    """Get a key from an object"""
    return (getattr(obj, '__getitem__', None) or getattr(obj, '__getattribute__'))(key)


def get_keys(obj):
    """Get context keys from an object"""
    if hasattr(obj, '__getitem__'):
        if hasattr(obj, 'keys'):
            return list(obj.keys())
        else:
            return [i for i, _v in enumerate(obj)]
    else:
        return [k for k in dir(obj) if not k.startswith('_')]


def get_moya_interface(context, obj):
    """Get a Moya context interface, from an object if available"""
    if hasattr(obj, '__moyacontext__'):
        return obj.__moyacontext__(context)
    return obj


def get_moya_attribute(context, obj, key, default=None):
    obj = get_moya_interface(context, obj)
    try:
        return getattr(obj, key, default)
    except Exception as e:
        return MoyaAttributeError(text_type(e))


def yield_join(seq, join=", "):
    """Iterate over a sequence, inserting join text between values"""
    iter_seq = iter(seq)
    value = next(iter_seq)
    while 1:
        yield value
        value = next(iter_seq)
        yield join


def to_expression(context, obj, max_size=None, truncate_text=" [...]"):
    """Convert an object to a Moya expression, where possible"""

    if context is None:
        from .. import pilot
        context = pilot.context

    if context is not None:
        obj = get_moya_interface(context, obj)

    def iter_dict(obj, sep=', '):
        i = iteritems(obj)
        k, v = next(i)
        while 1:
            for token in moya_repr(k):
                yield token
            yield ": "
            for token in moya_repr(v):
                yield token
            k, v = next(i)
            yield sep

    def iter_seq(obj, sep=', '):
        i = iter(obj)
        value = next(i)
        while 1:
            for token in moya_repr(value):
                yield token
            value = next(i)
            yield sep

    def moya_repr(obj):
        if isinstance(obj, text_type):
            yield quote_string(obj)
        elif obj is None:
            yield "None"
        elif isinstance(obj, bool):
            if obj:
                yield 'yes'
            else:
                yield 'no'
        elif hasattr(obj, '__moyarepr__'):
            yield obj.__moyarepr__(context)
        elif isinstance(obj, number_types):
            yield text_type(obj).rstrip('L')
        elif isinstance(obj, (list, tuple)):
            yield '['
            for value in iter_seq(obj):
                yield value
            yield ']'
        elif isinstance(obj, dict):
            yield '{'
            for token in iter_dict(obj):
                yield token
            yield '}'
        elif isinstance(obj, set):
            yield 'set:['
            for value in iter_seq(obj):
                yield value
            yield ']'
        else:
            # A last resort, may not be a valid Moya expression
            yield repr(obj)
    if max_size is None:
        return ''.join(moya_repr(obj))

    components = []
    append = components.append
    size = 0
    for c in moya_repr(obj):
        append(c)
        size += len(c)
        if size > max_size:
            # Try not to truncate the middle of a token if possible
            if size > 50 and len(components) > 1 and len(components[-1]) < 20:
                components.pop()
            return ''.join(components)[:max_size] + truncate_text
    return ''.join(components)


def get_app_from_callstack(context):
    call = context.get('.call', None)
    return getattr(call, 'app', None) or context.get('._t.app', None)


def set_dynamic(context):
    """Set commonly used dynamic items on the stack"""
    from .expressiontime import ExpressionDateTime
    context.set_dynamic('.clock', lambda c: ExpressionDateTime.moya_utcnow())
    context.set_counter('.counter')
    context.set_dynamic('.app', get_app_from_callstack)
    context.set_dynamic('.time', lambda c: time.time())
    theme_fs = context.get('.fs.themes', None)
    from ..theme import Theme
    if theme_fs:
        context.set_lazy('.theme', Theme.loader(theme_fs), None)
    else:
        context.set_lazy('.theme', Theme.dummy_loader, None)


STRING_ENCODE = {
    '\a': '\\a',
    '\b': '\\b',
    '\f': '\\f',
    '\n': '\\n',
    '\r': '\\r',
    '\t': '\\t',
    '\v': '\\v',
    "'": "\\'",
    '"': '\\"',
    '\\': '\\\\'
}

STRING_DECODE = {v: k for k, v in STRING_ENCODE.items()}

_encode_string = ('|'.join(re.escape(c) for c in STRING_ENCODE.keys()))
_decode_string = ('|'.join(re.escape(c) for c in STRING_DECODE.keys() if c != '"'))
_re_encode_string = re.compile(_encode_string)
_re_decode_string = re.compile(_decode_string)


def encode_string(s, _re_sub=_re_encode_string.sub, _replace=STRING_ENCODE.__getitem__):
    return _re_sub(lambda match: _replace(match.group(0)), s)


def quote_string(s):
    return "'{}'".format(encode_string(s))


def decode_string(s, _re_sub=_re_decode_string.sub, _replace=STRING_DECODE.__getitem__):
    return _re_sub(lambda match: _replace(match.group(0)), s)


if __name__ == "__main__":

    tests = [
        "test",
        "hello\nworld",
        "you can \"quote me\" on that"
    ]

    for t in tests:
        print()
        print(repr(t))

        enc = encode_string(t)

        print(repr(enc))

        dec = decode_string(enc)

        print(repr(dec))



# if __name__ == "__main__":
#     from moya.context import Context
#     c = Context()
#     c['foo'] = [range(10)] * 10000
#     c['bar'] = [{'a': "Hello world!", 'b': range(5)}] * 10000
#
#     print(c.to_expr(c['foo']))
#     print(c.to_expr(c['bar']))

# if __name__ == "__main__":
#     from moya.context.expressionrange import *
#     from moya.context.expressiontime import *

#     print(to_expression(context, "hello\nworld"))
#     from collections import OrderedDict

#     print(to_expression(context, OrderedDict()))

#     from moya.console import Console
#     c = Console()
#     c.obj(context, {'a': OrderedDict()})
