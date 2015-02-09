from __future__ import unicode_literals
from __future__ import print_function

from ..cache import Cache
from ..compat import iteritems

from time import time as get_time


class DictCache(Cache):
    """A local memory based cache"""
    cache_backend_name = "dict"

    def __init__(self, name, namespace, compress=False, compress_min=1024):
        super(DictCache, self).__init__(name,
                                        namespace,
                                        compress=compress,
                                        compress_min=compress_min)
        self.values = {}

    def encode_value(self, value):
        return value

    def decode_value(self, value):
        return value

    def _get(self, key, default):
        key = self.get_key(key)
        if key not in self.values:
            return default
        expire_time, value = self.values.get(key, default)
        if expire_time and expire_time <= get_time():
            del self.values[key]
            return default
        return self.decode_value(value)

    def _set(self, key, value, time):
        key = self.get_key(key)
        if time:
            expire = get_time() + time / 1000.0
        else:
            expire = None
        value = self.encode_value(value)
        self.values[key] = (expire, value)

    def _delete(self, key):
        key = self.get_key(key)
        try:
            del self.values[key]
        except KeyError:
            return False
        else:
            return True

    def evict(self):
        t = get_time()
        with self.lock:
            delete_keys = []
            for k, (expire_time, v) in iteritems(self.values):
                if expire_time and expire_time <= t:
                    delete_keys.append(k)
            for k in delete_keys:
                del self.values[k]


if __name__ == "__main__":
    from time import sleep
    d = DictCache('test', 'testing')
    d.set('key', 'myvalue', time=1)
    print(d.get('key', None))
    sleep(.6)
    print(d.get('key', None))
    sleep(.6)
    print(d.get('key', None))
