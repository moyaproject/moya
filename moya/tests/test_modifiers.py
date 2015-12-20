from __future__ import unicode_literals
from __future__ import print_function

import unittest
import datetime

from pytz import UTC

from moya.context import modifiers
from moya.context import Context


class _Choices(object):
    choices = [1, 2, 3]
    intchoices = [2, 3, 4]


class Mock(object):
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class Missing(object):
    moya_missing = True


class TestModifiers(unittest.TestSuite):

    def setUp(self):
        self.modifiers = modifiers.ExpressionModifiers()

    def testModifiers(self):
        m = self.modifiers

        c = Context()

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

        assert m.filesize(c, 1024) == '1.0kB'
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


