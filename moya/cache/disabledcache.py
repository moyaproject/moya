from __future__ import unicode_literals

from .base import Cache


class DisabledCache(Cache):
    cache_backend_name = "disabled"
    enabled = False

    def get(self, key, default=None):
        return default

    def set(self, key, value, time=0):
        pass

    def delete(self, key):
        pass
