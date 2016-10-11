from __future__ import unicode_literals
from __future__ import print_function

from ..cache import Cache
from ..compat import text_type, string_types

from fs.opener import open_fs
from fs.errors import FSError

from time import time as get_time
import codecs


class FileCache(Cache):
    """Caches in the filesystem"""
    cache_backend_name = "file"

    def __init__(self, name, namespace, fs=None, compress=False, compress_min=1024):
        super(FileCache, self).__init__(name,
                                        namespace,
                                        compress=compress,
                                        compress_min=compress_min,
                                        thread_safe=True)
        if fs is None:
            fs = open_fs('filecache', create=True)
        elif isinstance(fs, string_types):
            fs = open_fs(fs, create=True)

        if namespace:
            sub_dir = namespace.replace('/', '-').replace(' ', '-')
            fs.makedir(sub_dir, recreate=True)
            fs = fs.opendir(sub_dir)
        self.fs = fs
        self.max_key_length = 80

    @classmethod
    def initialize(cls, name, settings):
        return cls(name,
                   settings.get('namespace', ''),
                   fs=settings['location'],
                   compress=settings.get_bool("compress", False),
                   compress_min=settings.get_int("compress_min", 1024 * 16))

    def _get_key(self, key):
        """Gets a key (binary string) that contains the namespace"""
        # Namespace is a dir, so no need to encode it in the filename
        key = self.shorten_key(key.encode('utf-8'))
        return key

    def make_path(self, key):
        return "{}.cache".format(codecs.encode(key, 'hex').decode('utf-8'))

    def _get(self, key, default):
        path = self.make_path(self.get_key(key))
        try:
            with self.fs.open(path, 'rb') as f:
                expire_time = f.readline().strip()
                if expire_time and float(expire_time) <= get_time():
                    self.fs.remove(path)
                    return default
                value = self.decode_value(f.read())
                return value
        except FSError:
            return default

    def _set(self, key, value, time):
        path = self.make_path(self.get_key(key))
        if time:
            expire = get_time() + time / 1000.0
        else:
            expire = None
        value = self.encode_value(value)
        try:
            with self.fs.open(path, 'wb') as f:
                if expire is None:
                    f.write(b'\n')
                else:
                    text_type(expire)
                    f.write(text_type(expire).encode('utf-8') + b'\n')
                f.write(value)
        except FSError:
            pass

    def _delete(self, key):
        path = self.make_path(self.get_key(key))
        self.fs.remove(path)

    def _contains(self, key):
        path = self.make_path(self.get_key(key))
        return self.fs.isfile(path)

    def evict(self):
        t = get_time()
        for path in self.fs.listdir():
            if not path.endswith('.cache'):
                continue
            try:
                with self.fs.open(path, 'rb') as f:
                    try:
                        expire_time = float(f.readline().strip())
                    except (TypeError, ValueError):
                        # No expire time present, or format error
                        continue
                if expire_time and expire_time <= t:
                    self.fs.remove(path)
            except FSError:
                # Other processes may be evicting keys, so an FSError may not indicate a real problem
                pass

if __name__ == "__main__":
    from time import sleep
    d = FileCache('test', 'mem://')
    d.set('key', 'myvalue', time=1)
    print(d.get('key', None))
    sleep(.6)
    print(d.get('key', None))
    sleep(.6)
    print(d.get('key', None))
