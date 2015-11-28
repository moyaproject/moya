from __future__ import unicode_literals
from __future__ import print_function

from .compat import quote_plus, text_type


def _iter_qs_map(qs_map):
    for k, v in qs_map.items():
        if isinstance(v, list):
            for _v in v:
                yield text_type(k), text_type(_v)
        else:
            yield text_type(k), text_type(v)


def urlencode(query, _quote_plus=quote_plus, _iter_qs=_iter_qs_map):
    """url encode a mapping of query string values"""
    # Works slightly differently to Pythons urlencode
    # This function accepts lists and values, to generate multiple keys. e.g {'foo': ['bar', 'baz']} -> "foo=bar&foo=baz"
    # It will also remove the = if the value is empty, e.g. {'foo': ''} -> "foo"
    qs = "&".join("{}={}".format(_quote_plus(k), _quote_plus(v)) if text_type(v) else _quote_plus(k)
                  for k, v in _iter_qs(query))
    return qs
