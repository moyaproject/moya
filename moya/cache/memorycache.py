from __future__ import unicode_literals
from __future__ import print_function

from ..cache import Cache

from collections import OrderedDict, namedtuple
from time import time as get_time
import logging


log = logging.getLogger('moya.runtime')


CacheEntry = namedtuple("CacheEntry", "value,expire_time")


class MemoryCache(Cache):
    """Caches in a memcached server"""
    cache_backend_name = "memory"

    def __init__(self, name, namespace, compress=True, compress_min=1024, size=1024*1024):
        super(MemoryCache, self).__init__(
            name,
            namespace,
            compress=compress,
            thread_safe=False)
        self.max_size = size
        self.entries = OrderedDict()
        self.size = 0

    @classmethod
    def initialize(cls, name, settings):
        return cls(
            name,
            settings.get('namespace', ''),
            compress=settings.get_bool('compress', True),
            compress_min=settings.get_int("compress_min", 16 * 1024),
            size=settings.get_int('size', 1024) * 1024,
        )

    def evict_entry(self, key):
        """Evict a single key."""
        if key in self.entries:
            entry = self.entries.pop(key)
            self.size -= entry.value

    def reclaim(self, num_bytes):
        """Reclaim at least `num_bytes`"""
        log.debug('%r size=%s bytes', self, self.size)
        log.debug('%r reclaiming %s bytes', self, num_bytes)
        reclaimed = 0
        while self.entries and reclaimed < num_bytes:
            key, entry = self.entries.popitem(last=False)
            log.debug("%r evicting %r", self, key)
            deleted_bytes_count = len(entry.value)
            self.size -= deleted_bytes_count
            reclaimed += deleted_bytes_count
        return reclaimed >= num_bytes

    def _get(self, key, default):
        try:
            value_bytes = self.entries[key].value
        except KeyError:
            return default

        # Remove entry from cache
        entry = self.entries.pop(key)
        self.size -= len(entry.value)

        # If it has expired return the default
        if entry.expire_time and get_time() > entry.expire_time:
            return default

        # Otherwise put it back in to the cache at first position
        self.entries[key] = entry
        self.size += len(entry.value)

        return self.decode_value(value_bytes)

    def _set(self, key, value, time):
        value_bytes = self.encode_value(value)
        value_size = len(value_bytes)
        if value_size > self.max_size:
            return
        self.evict_entry(key)
        if self.size + value_size > self.max_size:
            if not self.reclaim(self.size + value_size - self.max_size):
                return
        expire_time = None if time is None else get_time() + time / 1000.0
        self.entries[key] = CacheEntry(value_bytes, expire_time)
        self.size += value_size

    def _delete(self, key):
        if key in self.entries:
            self.size -= len(self.entries.pop(key).value)
