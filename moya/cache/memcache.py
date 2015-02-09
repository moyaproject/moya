from __future__ import unicode_literals
from __future__ import print_function

from ..cache import Cache
from .. import errors
try:
    import pylibmc
except ImportError:
    pylibmc = None

from math import ceil

import logging
log = logging.getLogger('moya.runtime')


class MemCache(Cache):
    """Caches in a memcached server"""
    cache_backend_name = "memcache"

    def __init__(self, name, namespace, compress=False, compress_min=1024, hosts=None, connection_pool_size=10):
        super(MemCache, self).__init__(name,
                                       namespace,
                                       compress=False,
                                       thread_safe=True)
        if pylibmc is None:
            raise errors.StartupFailedError("'pylibmc' module is required for cache type 'memcache' (see https://pypi.python.org/pypi/pylibmc)")

        if not hosts:
            log.warning("{} no 'hosts' setting supplied for memcache server, using '127.0.0.1'".format(self))
            hosts = ["127.0.0.1"]
        mc = pylibmc.Client(hosts,
                            binary=True,
                            behaviors={'tcp_nodelay': True,
                                       'ketama': True})
        self.pool = pylibmc.ClientPool()
        self.pool.fill(mc, connection_pool_size)
        self.memcache_min_compress_len = 0 if not compress else max(1, compress_min)
        self.max_key_length = 200

    @classmethod
    def initialize(cls, name, settings):
        return cls(name,
                   settings.get('namespace', ''),
                   hosts=settings.get_list("hosts"),
                   compress=settings.get_bool("compress", True),
                   compress_min=settings.get_int("compress_min", 1024))

    def _get(self, key, default):
        key = self.get_key(key)
        with self.pool.reserve() as mc:
            found = mc.get(key)
            if found is None:
                return default
        return found

    def _set(self, key, value, time):
        time_sec = int(ceil(time / 1000.0))
        key = self.get_key(key)
        with self.pool.reserve() as mc:
            mc.set(key,
                   value,
                   time=time_sec,
                   min_compress_len=self.memcache_min_compress_len)

    def _delete(self, key):
        key = self.get_key(key)
        with self.pool.reserve() as mc:
            return mc.delete(key)
