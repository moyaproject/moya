from __future__ import unicode_literals
import unittest
import time

from fs.memoryfs import MemoryFS

from moya import cache

from nose.plugins.attrib import attr

try:
    import pylibmc
except:
    pylibmc = None


@attr('slow')
class CacheTests(object):

    long_key = "longkey" * 100

    def setUp(self):
        print(self)

    def tearDown(self):
        pass

    def test_long_key(self):
        """Test long keys"""
        key = self.long_key
        value = ["hello", "world"]
        self.assertEqual(self.cache.get(key, None), None)
        self.cache.set(key, value)
        self.assertEqual(self.cache.get(key, None), value)
        self.assertEqual(self.cache.get("nokey", None), None)

    def test_set(self):
        """Test set/get"""
        value = ["hello", "world"]
        self.assertEqual(self.cache.get("key", None), None)
        self.cache.set("key", value)
        self.assertEqual(self.cache.get("key", None), value)
        self.assertEqual(self.cache.get("nokey", None), None)

    def test_set_time(self):
        """Test set with expire time"""
        # Only way to test this is an arbitrary sleep
        # Some implementation only support whole seconds, so we have to sleep for 1 second
        value = ["hello", "world"]
        self.cache.set("key", value, time=1000)
        self.assertEqual(self.cache.get("key", None), value)
        time.sleep(1.1)  # Plus a margin of error
        self.assertEqual(self.cache.get("key", None), None)

    def test_delete(self):
        """Test delete"""
        value = ["hello", "world"]
        self.assertEqual(self.cache.get("key", None), None)
        self.cache.set("key", value)
        self.assertEqual(self.cache.get("key", None), value)
        self.cache.delete("key")
        self.assertEqual(self.cache.get("key", None), None)

    def test_contains(self):
        """Test contains"""
        value = ["hello", "world"]
        self.assert_(not self.cache.contains("key"))
        self.assert_("key" not in self.cache)
        self.cache.set("key", value)
        self.assert_(self.cache.contains("key"))
        self.assert_("key" in self.cache)
        self.cache.delete("key")
        self.assert_(not self.cache.contains("key"))
        self.assert_("key" not in self.cache)


class NamespacesTests(object):
    """For caches that share storage"""

    def test_namespaces(self):
        """Test multiple namespaces on cache"""
        value = ["hello", "world"]
        value2 = ["goodybye", "world"]
        self.cache.set("key", value)
        self.assert_("key" in self.cache)
        self.assert_("key" not in self.cache2)
        self.cache2.set("key", value2)
        self.assertEqual(self.cache.get("key", None), value)
        self.assertEqual(self.cache2.get("key", None), value2)


class TestDictCache(unittest.TestCase, CacheTests):

    def setUp(self):
        self.cache = cache.dictcache.DictCache("test", "")


class TestFileCache(unittest.TestCase, CacheTests, NamespacesTests):

    __test__ = True

    def setUp(self):
        self.fs = MemoryFS()
        self.cache = cache.filecache.FileCache("test", "ns1", fs=self.fs)
        self.cache2 = cache.filecache.FileCache("test", "ns2", fs=self.fs)

    def tearDown(self):
        self.fs.close()
        self.fs = None


class TestMemcacheCache(unittest.TestCase, CacheTests, NamespacesTests):

    __test__ = bool(pylibmc)

    def setUp(self):
        self.cache = cache.memcache.MemCache("test", "ns1", hosts=["127.0.0.1"])
        self.cache2 = cache.memcache.MemCache("test", "ns2", hosts=["127.0.0.1"])

    def tearDown(self):
        # It would probably be better to start / restart the server
        # but that would be a major headache
        # TODO: delete keys out of band

        self.cache.delete("key")
        self.cache2.delete("key")
        self.cache.delete(CacheTests.long_key)
        self.cache2.delete(CacheTests.long_key)


class TestDictCompressCache(unittest.TestCase, CacheTests):
    """Test with compression enabled"""

    __test__ = True

    def setUp(self):
        self.cache = cache.dictcache.DictCache("test", "", compress=True, compress_min=1)


class TestDebugWrapper(unittest.TestCase, CacheTests):

    __test__ = True

    def setUp(self):
        self._cache = cache.dictcache.DictCache("test", "")
        self.cache = cache.base.DebugCacheWrapper(self._cache)


class TetstDisabledCache(unittest.TestCase):

    __test__ = True

    def setUp(self):
        self.cache = cache.disabledcache.DisabledCache("test", "")

    def test_disabled(self):
        """Test disabled cache"""
        value = ["hello", "world"]
        self.assert_(not self.cache.contains("key"))
        self.cache.set("key", value)
        self.assert_(not self.cache.contains("key"))
        self.assertEqual(self.cache.get("key", None), None)
        self.cache.delete("key")
