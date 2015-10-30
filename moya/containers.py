from __future__ import unicode_literals
from __future__ import print_function

from .compat import PY2, text_type, implements_to_string
from .urltools import urlencode

from threading import Lock

if PY2:
    from urlparse import parse_qsl
else:
    from urllib.parse import parse_qsl


from collections import OrderedDict


class LRUCache(OrderedDict):
    """A dictionary-like container that stores a given maximum items.

    If an additional item is added when the LRUCache is full, the least recently used key is
    discarded to make room for the new item.

    """
    def __init__(self, cache_size=None):
        self.cache_size = cache_size
        self.lock = Lock()
        super(LRUCache, self).__init__()

    def __reduce__(self):
        return self.__class__, (self.cache_size,)

    def __setitem__(self, key, value):
        with self.lock:
            if self.cache_size is not None and key not in self:
                if len(self) >= self.cache_size:
                    self.popitem(last=False)
            OrderedDict.__setitem__(self, key, value)

    def lookup(self, key):
        with self.lock:
            value = OrderedDict.__getitem__(self, key)
            del self[key]
            OrderedDict.__setitem__(self, key, value)
            return value


@implements_to_string
class QueryData(OrderedDict):
    """A container for data encoded in a url query string"""

    @classmethod
    def from_qs(cls, qs, change_callback=None):
        qd = cls()
        for k, v in parse_qsl(qs, keep_blank_values=True, strict_parsing=False):
            qd.setdefault(k, []).append(v)
        return qd

    def copy(self):
        return OrderedDict(self)

    def update(self, d):
        """Specialized update, setting a value to None will delete it. Also ensures that the query data contains lists"""
        for k, v in d.items():
            if v is None:
                if k in self:
                    del self[k]
            else:
                if isinstance(v, (list, set, tuple, dict)) or hasattr(v, 'items'):
                    self[k] = list(v)
                else:
                    if v is None:
                        v = ''
                    elif not isinstance(v, text_type):
                        v = text_type(v)
                    self[k] = [v]

    def __str__(self):
        return urlencode(self)

    def __repr__(self):
        return '<querydata "{}">'.format(urlencode(self))

    def __setitem__(self, k, v):
        if v is None:
            ret = self.__delitem__(k)
        else:
            if isinstance(v, (set, tuple)):
                v = list(v)
            if not isinstance(v, list):
                v = [text_type(v)]
            ret = super(QueryData, self).__setitem__(k, v)
        return ret

    def __delitem__(self, k):
        ret = super(QueryData, self).__delitem__(k)
        return ret


if __name__ == "__main__":
    qd = QueryData.from_qs('foo=bar&a=1&b=2&hobbit=frodo&hobbit=sam')

    print(qd.items())

    qd.update({'foo': None})

    print(qd.items())
