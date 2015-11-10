from __future__ import unicode_literals
from __future__ import print_function

from moya import tools
from moya.context.missing import Missing
from moya.compat import text_type
from moya.elements.elementbase import ReturnContainer

import pytz
import datetime
import unittest
import io
import os.path


class TestTools(unittest.TestCase):

    def test_extract_namespace(self):
        tests = [
            ("{http://moyaproject.com}test1", ("http://moyaproject.com", "test1")),
            ("test2", ("http://moyaproject.com", "test2")),
            ("{http://moyaproject.com/db}query", ("http://moyaproject.com/db", "query"))
        ]
        for test, result in tests:
            self.assertEqual(tools.extract_namespace(test), result)

    def test_asint(self):
        assert tools.asint('5') == 5
        assert tools.asint('-5') == -5
        assert tools.asint('foo', 3) == 3

    def test_match_exception(self):

        tests = [
            ("*", 'anything', True),
            ("foo", "foo", True),
            ("foo.bar", "foo.bar", True),
            ("foo.*", "foo.bar", True),
            ("foo.*", "foo.bar.baz", True),
            ("bar", "foo", False),
            ("foo.bar.*", "foo.baz.egg", False)
        ]

        for m, exc, result in tests:
            print(exc, m, result)
            assert tools.match_exception(exc, m) == result

    def test_md5_hexdigest(self):
        assert tools.md5_hexdigest('foo') == 'acbd18db4cc2f85cedef654fccc4a4d8'

    def test_check_missing(self):
        tools.check_missing({'foo': 'bar'})
        try:
            tools.check_missing({'foo': Missing('bar')})
        except ValueError:
            pass
        else:
            assert False

    def test_timer(self):
        with tools.timer('foo'):
            pass
        with tools.timer('foo', ms=True):
            pass
        with tools.timer('foo', write_file="/tmp/__timertest__"):
            pass

    def test_parse_timedelta(self):
        assert tools.parse_timedelta('10') == 10
        assert tools.parse_timedelta('10s') == 10 * 1000
        assert tools.parse_timedelta('1m') == 60 * 1000
        try:
            tools.parse_timedelta('agfdwrg')
        except ValueError:
            assert True
        else:
            assert False

    def test_get_moya_dir(self):
        moya_dir = os.path.join(os.path.dirname(__file__), 'moyadir')
        path = os.path.join(moya_dir, 'foo')
        assert tools.get_moya_dir(path) == moya_dir
        try:
            tools.get_moya_dir()
        except ValueError:
            assert True
        else:
            assert False
        try:
            tools.get_moya_dir('/')
        except ValueError:
            assert True
        else:
            assert False

    def test_is_moya_dir(self):
        moya_dir = os.path.join(os.path.dirname(__file__), 'moyadir')
        path = os.path.join(moya_dir, 'foo')
        assert not tools.is_moya_dir(path)
        assert tools.is_moya_dir(moya_dir)
        assert not tools.is_moya_dir('/')
        assert not tools.is_moya_dir()

    def test_file_chunker(self):
        text = b"Hello, World"
        f = io.BytesIO(text)
        chunks = list(tools.file_chunker(f, 1))
        assert chunks == [b'H', b'e', b'l', b'l', b'o', b',', b' ', b'W', b'o', b'r', b'l', b'd']

        f = io.BytesIO(text)
        chunks = list(tools.file_chunker(f, 2))
        assert chunks == [b'He', b'll', b'o,', b' W', b'or', b'ld']

        f = io.BytesIO(text)
        chunks = list(tools.file_chunker(f, 256))
        assert chunks == [text]

    def test_make_id(self):
        assert tools.make_id() != tools.make_id()

    def test_datetime_to_epoch(self):
        assert tools.datetime_to_epoch(100) == 100
        epoch_start = datetime.datetime(1970, 1, 1, 0, 0, tzinfo=pytz.UTC)
        self.assertEqual(tools.datetime_to_epoch(epoch_start), 0)

    def test_split_commas(self):
        assert tools.split_commas('foo, bar') == ['foo', 'bar']

    def test_summarize_text(self):
        assert tools.summarize_text(None) == ''
        assert tools.summarize_text('hello') == 'hello'
        assert tools.summarize_text('hello, world', max_length=5) == 'hello[...]'

    def test_get_return(self):
        assert tools.get_return(None) == {}
        assert tools.get_return(100) == 100
        ret = ReturnContainer('foo')
        assert tools.get_return(ret) == 'foo'

    def test_as_dict(self):
        assert tools.as_dict({'foo': 'bar'}) == {'foo': 'bar'}

        class D(object):
            def items(self):
                return [('foo', 'bar')]

            def iteritems(self):
                return iter(self.items())
        d = D()
        assert tools.as_dict(d) == {'foo': 'bar'}

    def test_quote(self):
        assert tools.quote('hello') == '"hello"'

    def test_squote(self):
        assert tools.squote('hello') == "'hello'"

    def test_textual_list(self):
        assert tools.textual_list(["foo", "bar"]) == "'foo' or 'bar'"
        assert tools.textual_list(["foo", "bar", "baz"]) == "'foo', 'bar' or 'baz'"
        assert tools.textual_list(["foo"]) == "'foo'"
        assert tools.textual_list([], empty='nadda') == "nadda"

    def test_moya_update(self):
        d = {}
        tools.moya_update(d, {'foo': 'bar'})
        self.assertEqual(d, {'foo': 'bar'})

    def test_url_join(self):
        assert tools.url_join('http://moyaproject.com/', '/foo/') == 'http://moyaproject.com/foo/'

    def test_remove_padding(self):
        assert tools.remove_padding('    ') == ''
        assert tools.remove_padding('') == ''

        assert tools.remove_padding('  hello  ') == '  hello  '
        assert tools.remove_padding('\n\nhello\n\n') == 'hello'

        assert tools.remove_padding('\n\nhello\nworld\n\n') == 'hello\nworld'

    def test_unique(self):
        assert tools.unique([]) == []
        assert tools.unique(['foo']) == ['foo']
        assert tools.unique(['foo', 'bar']) == ['foo', 'bar']
        assert tools.unique(['foo', 'bar', 'bar', 'bar', 'baz']) == ['foo', 'bar', 'baz']
        assert tools.unique(5) == []

    def test_format_element_type(self):
        assert tools.format_element_type(('foo', 'bar')) == "{foo}bar"
        assert tools.format_element_type('foo') == "foo"

    # def test_get_ids(self):
    #     class O(object):
    #         id = 1
    #     assert tools.get_ids([O(), None]) == [1]

    def test_multi_replace(self):
        replacer = tools.MultiReplace({'foo': 'bar', 'baz': 'egg'})
        assert replacer('foo baz foo ok') == "bar egg bar ok"

    def test_dummy_lock(self):
        with tools.DummyLock() as _lock:
            pass

    def test_make_cache_key(self):
        assert tools.make_cache_key(['foo', 'bar']) == 'foo.bar'
        assert tools.make_cache_key(['foo', 'bar', [1, 2]]) == 'foo.bar.1-2'
        assert tools.make_cache_key(['foo', 'bar', [1, 2], {'foo': 'bar'}]) == 'foo.bar.1-2.foo_bar'

    def test_nearers_word(self):
        assert tools.nearest_word('floo', ['foo', 'bar']) == 'foo'

    def test_show_tb(self):
        @tools.show_tb
        def test():
            raise Exception('everything is fine')
        try:
            test()
        except:
            assert True
        else:
            assert False

    def test_normalize_url_path(self):
        assert tools.normalize_url_path('') == '/'
        assert tools.normalize_url_path('foo') == '/foo/'
        assert tools.normalize_url_path('foo/bar') == '/foo/bar/'

    def test_lazystr(self):
        s = tools.lazystr(lambda: 'foo')
        assert text_type(s) == 'foo'
        s = tools.lazystr(lambda: 'foo')
        assert len(s) == 3
        s = tools.lazystr(lambda: 'foo')
        assert s.upper() == 'FOO'
