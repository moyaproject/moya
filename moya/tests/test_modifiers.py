from __future__ import unicode_literals
from __future__ import print_function

import unittest
import datetime

from pytz import UTC
import io
import re

from moya.context import modifiers
from moya.context import Context
from moya.url import URL
from moya.versioning import Version, VersionSpec


class _Choices(object):
    choices = [1, 2, 3]
    intchoices = [2, 3, 4]


class Mock(object):
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __moyarenderable__(self, context):
        return "ok"


class Missing(object):
    moya_missing = True


class TestModifiers(unittest.TestCase):
    """Test modifiers in expressions."""

    def setUp(self):
        self.modifiers = modifiers.ExpressionModifiers()

    def testModifiers(self):
        m = self.modifiers

        c = Context({
            'call': {
                'world': "World!"
            },
            'permissions': ['read'],
            'request': {
                'path_qs': '/foo/bar/baz?page=1',
                'path': '/foo/bar/baz',
                'query_string': 'page=1'
            }
        })
        c.push_frame('call')

        assert m.abs(c, -5) == 5
        assert m.abs(c, 5) == 5
        assert m.abs(c, 0) == 0

        assert m.all(c, [1, 1, 1])
        assert not m.all(c, [1, 0, 1])
        assert m.all(c, [])

        # missing app:

        assert m.basename(c, 'foo') == 'foo'
        assert m.basename(c, 'foo/bar') == 'bar'

        assert m.bool(c, 1) is True
        assert m.bool(c, 0) is False

        assert m.capitalize(c, 'hello') == 'Hello'

        assert m.ceil(c, 3.14) == 4.0

        assert m.choices(c, _Choices()) == [1, 2, 3]

        assert m.intchoices(c, _Choices()) == [2, 3, 4]

        assert list(m.chain(c, [[1, 2], [3, 4]])) == [1, 2, 3, 4]

        assert m.chr(c, 32) == ' '

        assert m.collect(c, (['Hello', 'World'], 1)) == ['e', 'o']

        objs = [Mock(id=1, a='hello'), Mock(id=2, a='world')]
        assert m.collectmap(c, [objs, 'a']) == {'hello': objs[0], 'world': objs[1]}

        assert m.collectids(c, objs) == [1, 2]

        assert m.commalist(c, ['hello', 'world']) == 'hello,world'
        assert m.commaspacelist(c, ['hello', 'world']) == 'hello, world'
        assert m.commasplit(c, 'foo,bar') == ['foo', 'bar']

        assert m.copy(c, {'foo': 'bar'}) == {'foo': 'bar'}

        # missing csrf

        assert m.d(c, '3') == 3

        # missing data

        assert m.date(c, '2015-12-20') == datetime.date(2015, 12, 20)
        assert m.datetime(c, '2015-12-20T16:43:15.479619') == datetime.datetime(2015, 12, 20, 16, 43, 15, 479619, tzinfo=UTC)

        assert m.debug(c, 5) == '5'
        assert m.debug(c, '5') == "'5'"

        assert m.dict('c', [('foo', 'bar')]) == {'foo': 'bar'}

        assert m.dirname(c, 'foo/bar') == 'foo'

        assert m.domain(c, 'http://www.willmcgugan.com/foo/') == 'www.willmcgugan.com'

        assert m.dropchar(c, 'foo') == 'oo'

        # missing enum

        assert list(m.enumerate(c, 'foo')) == [(0, 'f'), (1, 'o'), (2, 'o')]
        assert list(m.enumerate1(c, 'foo')) == [(1, 'f'), (2, 'o'), (3, 'o')]

        assert m.epoch(c, 0) == datetime.datetime(1970, 1, 1, tzinfo=UTC)

        assert m.eval(c, '1+2') == 3

        assert m.exists(c, 'foo')
        assert not m.exists(c, Missing())

        assert m.ext('foo.bar', '.bar')

        assert m.filesize(c, 1024) == '1.0 KB'
        assert m.first(c, 'foo') == 'f'
        assert m.flat(c, [1, [2, 3]]) == [1, 2, 3]
        assert m.float(c, '3.14') == 3.14
        assert m.floor(c, 3.14) == 3
        assert m.parsejson(c, '''{"foo": "bar"}''') == {'foo': 'bar'}

        # missing get

        objs = [Mock(a='foo'), Mock(a='foo')]
        assert m.group(c, [objs, 'a'])['foo'] == [objs[0], objs[1]]

        # missing hasdata
        assert m.html(c, '<h1>header</h1>') == '<h1>header</h1>'
        assert hasattr(m.html(c, '<h1>header</h1>'), 'html_safe')

        objs = [Mock(id=1, a='hello'), Mock(id=2, a='world')]

        assert m.ids(c, objs) == [1, 2]

        assert m.int(c, '3') == 3
        assert m.int(c, 3.14) == 3

        assert m.isbool(c, True)
        assert m.isbool(c, False)
        assert not m.isbool(c, 0)

        assert not m.isemail(c, 'notanemal')
        assert m.isemail(c, 'email@example.org')

        assert m.isfloat(c, 3.14)
        assert not m.isfloat(c, '3.14')

        assert m.isint(c, 3)
        assert not m.isint(c, '3')

        assert m.isnone(c, None)
        assert not m.isnone(c, 'None')
        assert not m.isnone(c, 0)

        assert m.isnumber(c, 5)
        assert m.isnumber(c, 3.14)
        assert m.isnumber(c, -10)
        assert not m.isnumber(c, None)

        assert m.isstr(c, 'str')
        assert m.isstr(c, '')
        assert not m.isstr(c, 3)

        assert m.items(c, {'foo': 'bar'}) == [('foo', 'bar')]

        assert m.join(c, ['foo', 'bar']) == 'foobar'

        assert m.joinspace(c, ['foo', 'bar']) == 'foo bar'

        assert m.joinwith(c, (['foo', 'bar'], '-')) == 'foo-bar'

        assert m.keys(c, {'foo': 'bar'}) == ['foo']

        assert m.last(c, [1, 2, 3]) == 3

        assert m.len(c, [1, 2, 3, 4]) == 4

        assert m.linebreaks(c, 'a\nb') == 'a<br>\nb'

        assert m.list(c, 'abc') == ['a', 'b', 'c']

        # missing localize

        assert m.log10(c, 100.0) == 2.0

        assert m.lower(c, 'Hello') == 'hello'

        assert m.lstrip(c, '  \nHello\n') == 'Hello\n'

        assert m.max(c, [1, 2, 3, 0]) == 3

        assert m.md5(c, 'hello') == '5d41402abc4b2a76b9719d911017c592'
        assert m.md5(c, io.BytesIO(b'hello')) == '5d41402abc4b2a76b9719d911017c592'

        assert m.min(c, [1, 2, 3, 0]) == 0

        assert not m.missing(c, 'foo')
        assert m.missing(c, Missing())

        assert m.none(c, 0) is None
        assert m.none(c, 1) == 1

        assert m.partition(c, ['hello-world', '-']) == ('hello', '-', 'world')
        assert m.partition(c, 'hello world') == ('hello', ' ', 'world')

        assert m.parsedatetime(c, ['5/7/1974', '%d/%m/%Y']) == datetime.datetime(1974, 7, 5)

        assert m.rpartition(c, ['foo-bar-baz', '-']) == ('foo-bar', '-', 'baz')
        assert m.rpartition(c, 'foo bar baz') == ('foo bar', ' ', 'baz')

        assert isinstance(m.path(c, 'foo/bar'), modifiers.Path)

        assert m.slashjoin(c, ['foo/', '/bar']) == 'foo/bar'

        assert m.permission(c, 'read')
        assert not m.permission(c, 'write')

        assert m.prettylist(c, ['foo', 'bar']) == "'foo', 'bar'"

        assert m.qsupdate(c, {'page': '3'}) == 'page=3'

        assert m.quote(c, 'hello') == '"hello"'
        assert m.relto(c, '/bar') == '../../bar'

        # missing render

        assert m.renderable(c, Mock()) == 'ok'

        assert m.remap(c, {'foo': 'bar', 'baz': 'bar'}) in [{'bar': ['foo', 'baz']}, {'bar': ['baz', 'foo']}]

        assert list(m.reversed(c, [1, 3, 4])) == [4, 3, 1]

        assert m.rsorted(c, [1, 5, 2]) == [5, 2, 1]

        objs = [Mock(id=5), Mock(id=10)]
        assert m.rsortedby(c, [objs, 'id']) == [objs[1], objs[0]]

        assert m.round(c, 3.14) == 3
        assert m.round(c, [3.14, 1]) == 3.1

        assert m.rstrip(c, '  hello  ') == '  hello'
        assert m.safe(c, 'test') == 'test'
        assert hasattr(m.safe(c, 'test'), 'html_safe')

        assert m.seqlast(c, [1, 2]) == [(False, 1), (True, 2)]

        assert m.set(c, [1, 2]) == {1, 2}

        assert isinstance(m.slice(c, [1, 2]), slice)

        assert m.slug(c, 'hello world') == 'hello-world'

        assert m.sorted(c, [1, 3, 0]) == [0, 1, 3]

        objs = [Mock(n=50), Mock(n=0)]
        assert m.sortedby(c, [objs, 'n']) == [objs[1], objs[0]]

        assert m.split(c, 'foo bar baz') == ['foo', 'bar', 'baz']
        assert m.split(c, ['foo-bar-baz', '-']) == ['foo', 'bar', 'baz']

        assert m.splitfirst(c, 'foo bar baz') == 'foo'
        assert m.splitlast(c, 'foo bar baz') == 'baz'

        assert m.splitlines(c, 'foo\nbar') == ['foo', 'bar']
        assert m.squote(c, 'Hello') == "'Hello'"

        assert m.str(c, 5) == '5'

        assert m.strip(c, ' \nfoo \n ') == 'foo'
        self.assertEqual(m.stripall(c, ['a', ' b', 'c ', ' d ', '\t  e  \n\n ']), ['a', 'b', 'c', 'd', 'e'])

        assert m.striptags(c, '<p>Hello</p>') == ' Hello'
        assert m.sub(c, 'Hello ${world}') == 'Hello World!'

        assert m.sum(c, [1, 2, 3]) == 6

        assert m.swapcase(c, 'Hello') == 'hELLO'

        assert m.time(c, '09:45:30.0') == datetime.time(9, 45, 30)
        assert m.time(c, 'notatime') is None

        assert m.trim(c, ['longlonglong', 3]) == 'lon'

        assert m.ctime(c, 'Sun Jul  5 00:00:00 2015') == datetime.datetime(2015, 7, 5)

        assert m.timespan(c, '1d').hours == 24

        assert m.title(c, 'hello world') == 'Hello World'

        assert len(m.token(c, 3)) == 3

        assert m.json(c, [5]) == "[5]"
        assert m.type(c, 5) is type(5)

        assert m.unique(c, [1, 1, 2, 3]) == [1, 2, 3]

        assert m.upper(c, 'hello') == 'HELLO'

        assert isinstance(m.url(c, 'http://www.moyaproject.com'), URL)

        assert m.urldecode(c, 'foo=bar').copy() == {'foo': ['bar']}

        assert 'foo=egg' in m.urlupdate(c, {'foo': 'egg'})

        assert m.urlunquote(c, '%20') == ' '
        assert m.urlquote(c, ' ') == '%20'

        re_uuid = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
        assert re_uuid.match(m.uuid(c, 1))
        assert re_uuid.match(m.uuid(c, 4))
        assert re_uuid.match(m.uuid(c, [3, 'http://www.moyaproject']))

        assert m.validfloat(c, '5')
        assert m.validfloat(c, '3.14')
        assert not m.validfloat(c, '3.14.3')

        assert m.validint(c, '5')
        assert m.validint(c, 5)
        assert not m.validint(c, '5.3')

        assert m.values(c, {'foo': 'bar'}) == ['bar']

        assert m.version(c, '3.2.3').major == 3
        assert isinstance(m.version(c, '3.2.3'), Version)

        self.assertEqual(m.zip(c, [[1, 2], [3, 4]]), [(1, 3), (2, 4)])

        assert m.versionspec(c, 'moya.tests==1.0.0').name == 'moya.tests'
        assert isinstance(m.versionspec(c, 'moya.tests==1.0.0'), VersionSpec)
