from __future__ import unicode_literals
from __future__ import print_function

import unittest
from moya.context import Context
from moya.context import dataindex


class TestDataIndex(unittest.TestCase):

    def test_parse(self):
        """Test dataindex parse"""
        tests = [("", []),
                 (".", []),
                 ('""', [""]),
                 ("\\\\", ["\\"]),
                 ("foo", ["foo"]),
                 ("foo.bar", ["foo", "bar"]),
                 (".foo.bar", ["foo", "bar"]),
                 ("foo.bar.baz", ["foo", "bar", "baz"]),
                 ('"foo"', ["foo"]),
                 ('"foo".bar', ["foo", "bar"]),
                 ('"foo.bar"', ["foo.bar"]),
                 ('foo\.bar', ["foo.bar"]),
                 ("1", [1]),
                 ('"1"', ["1"]),
                 ('foo.2', ["foo", 2]),
                 ]
        for index, parsed in tests:
            self.assertEqual(dataindex.parse(index), parsed)

    def test_build(self):
        """Test encoding indices as a dataindex string"""
        self.assertEqual(dataindex.build(['Hello', 'World', 1]), 'Hello.World.1')
        self.assertEqual(dataindex.build(['Hello']), 'Hello')

    def test_join(self):
        """Test joining of indices"""
        self.assertEqual(dataindex.join('foo'), 'foo')
        self.assertEqual(dataindex.join('foo', 'bar.baz'), 'foo.bar.baz')
        self.assertEqual(dataindex.join('foo', 'bar\.baz'), 'foo."bar.baz"')
        self.assertEqual(dataindex.join('foo', '"bar.baz"'), 'foo."bar.baz"')
        self.assertEqual(dataindex.join('foo', 'bar.baz.1:5'), 'foo.bar.baz.1:5')
        self.assertEqual(dataindex.join('foo', 'bar', 'baz'), 'foo.bar.baz')
        self.assertEqual(dataindex.join('foo', ['bar', 'baz']), 'foo.bar.baz')
        self.assertEqual(dataindex.join('.foo', 'bar', 'baz'), '.foo.bar.baz')
        self.assertEqual(dataindex.join('foo', '.bar', 'baz'), '.bar.baz')

    def test_normalize(self):
        """Test normalizing indices"""
        self.assertEqual(dataindex.normalize("foo"), "foo")
        self.assertEqual(dataindex.normalize(r"\foo"), "foo")
        self.assertEqual(dataindex.normalize(r"\f\o\o"), "foo")
        self.assertEqual(dataindex.normalize('"foo"'), "foo")

    def test_make_absolute(self):
        """Test making a data index absolute"""
        self.assertEqual(dataindex.make_absolute('foo.bar'), '.foo.bar')
        self.assertEqual(dataindex.make_absolute('.foo.bar'), '.foo.bar')

    def test_iter_index(self):
        """Test iter_index method"""
        self.assertEqual(list(dataindex.iter_index('foo.bar.baz')), [('foo', 'foo'),
                                                                     ('bar', 'foo.bar'),
                                                                     ('baz', 'foo.bar.baz')])


class TestContext(unittest.TestCase):

    def setUp(self):
        pass

    def test_basic_root(self):
        """Test basic operations from root"""
        c = Context()
        c['foo'] = 'bar'
        self.assert_('foo' in c)
        self.assertEqual(c['foo'], 'bar')
        self.assertEqual(c.root['foo'], 'bar')
        c['fruit'] = 'apple'
        self.assert_('fruit' in c)
        self.assertEqual(c['fruit'], 'apple')
        self.assertEqual(c.root['fruit'], 'apple')
        self.assertEqual(c.get('nothere', 'missing'), 'missing')
        self.assertEqual(sorted(c.keys()), ['foo', 'fruit'])
        self.assertEqual(sorted(c.values()), ['apple', 'bar'])
        self.assertEqual(sorted(c.items()), [('foo', 'bar'), ('fruit', 'apple')])

    def test_attr(self):
        """Test attribute / getitem distinction"""
        class A(object):
            foo = "buzz"
            bar = "cantsee"

            def __getitem__(self, key):
                if key == 'foo':
                    return "baz"
                raise IndexError(key)

            def __contains__(self, key):
                return key == 'foo'

        c = Context()
        c["a"] = A()
        self.assertEqual(c["a.foo"], "baz")
        self.assert_(c['a.bar'].moya_missing)
        #self.assertRaises(errors.ContextKeyError, c.__getitem__, "a.bar")
        self.assert_("a.bar" not in c)
        self.assert_("a.foo" in c)

    def test_get_root(self):
        """Test looking up root object"""
        c = Context({'foo': [1, 2, 3]})
        self.assertEqual(c[''], {'foo': [1, 2, 3]})
        c.push_frame('foo')
        self.assertEqual(c[''], [1, 2, 3])
        c.push_frame('.foo')
        self.assertEqual(c[''], [1, 2, 3])
        c.push_frame('.')
        self.assertEqual(c[''], {'foo': [1, 2, 3]})

    def test_inspect(self):
        """Test keys/values/items"""
        c = Context()
        c['foo'] = dict(a=1, b=2, c=3)
        c['bar'] = ['a', 'b', 'c']

        def compare(a, b):
            a = sorted(a, key=lambda k: str(k.__class__.__name__))
            b = sorted(b, key=lambda k: str(k.__class__.__name__))

            for compare_a, compare_b in zip(a, b):
                self.assertEqual(compare_a, compare_b)

        self.assertEqual(sorted(c.keys()), ['bar', 'foo'])
        self.assertEqual(sorted(c.keys('foo')), ['a', 'b', 'c'])
        self.assertEqual(sorted(c.keys('bar')), [0, 1, 2])

        compare((c.values()), [dict(a=1, b=2, c=3), ['a', 'b', 'c']])
        self.assertEqual(sorted(c.values('foo')), [1, 2, 3])
        self.assertEqual(sorted(c.values('bar')), ['a', 'b', 'c'])

        compare(sorted(c.items()), sorted([('foo', dict(a=1, b=2, c=3)), ('bar', ['a', 'b', 'c'])]))
        self.assertEqual(sorted(c.items('foo')), [('a', 1), ('b', 2), ('c', 3)])
        self.assertEqual(sorted(c.items('bar')), [(0, 'a'), (1, 'b'), (2, 'c')])

        self.assertEqual(sorted(c.all_keys()), sorted(['', 'foo', 'foo.a', 'foo.c', 'foo.b', 'bar', 'bar.0', 'bar.1', 'bar.2']))

    def test_frame_stack(self):
        """Test push/pop frame operations"""
        c = Context()
        c['foo'] = {}
        c.push_frame('foo')
        self.assertEqual(c.get_frame(), '.foo')
        c['bar'] = 1
        self.assertEqual(c.root['foo']['bar'], 1)
        c.pop_frame()
        self.assertEqual(c.get_frame(), '.')
        c['baz'] = 2
        self.assertEqual(c.root['baz'], 2)

    def test_root_indices(self):
        """Test root indices"""
        c = Context()
        c['foo'] = {}
        c['baz'] = 2
        c.push_frame('foo')  # In .foo
        c['bar'] = 1
        self.assertEqual(c['.baz'], 2)
        self.assertEqual(c['bar'], 1)
        c.push_frame('.')  # In .
        self.assertEqual(c['baz'], 2)
        self.assertEqual(c['foo.bar'], 1)
        c.pop_frame()  # In .foo
        self.assertEqual(c['.baz'], 2)
        self.assertEqual(c['bar'], 1)
        self.assertEqual(c['.foo.bar'], 1)

    def test_expressions(self):
        """Test expression evaluation"""
        c = Context()
        c['foo'] = {}
        c['baz'] = 2
        c['foo.a'] = 10
        c['foo.b'] = 20
        c['foo.c'] = dict(inception="three levels")
        c['word'] = 'apples'
        c['word2'] = c['word']
        c['lt'] = "less than"

        class ChoiceTest(object):
            def __init__(self):
                self.choices = []

        c['choicetest'] = ChoiceTest()

        class Obj(object):
            def __init__(self, id):
                self.id = id

        c['objects'] = [Obj(1), Obj(2), Obj(3)]

        tests = [('1', 1),
                 ('123', 123),
                 ('"1"', "1"),
                 ("'1'", "1"),
                 ('"\\""', '"'),
                 ("'''1'''", "1"),
                 ('"""1"""', "1"),
                 ('100-5', 95),
                 ('7//2', 3),
                 ('1+1', 2),
                 ('1+2+3', 6),
                 ('2+3*2', 8),
                 ('(2+3)*2', 10),
                 ('foo.a', 10),
                 ('$foo.a', 10),
                 ('$lt', "less than"),
                 ('foo.c.inception', "three levels"),
                 #('foo.c.inception.:5 + " "+"little pigs"', "three little pigs"),
                 #('foo.c.inception.::-1', "slevel eerht"),
                 ('foo.a+foo.b', 30),
                 ('.foo.a+.foo.b', 30),
                 ('foo.a/2', 5),
                 ('foo.a/4', 2.5),
                 ('word*3', 'applesapplesapples'),
                 ('word.2*3', 'ppp'),
                 ('word+str:2', 'apples2'),
                 ('word^="a"', True),
                 ('word^="app"', True),
                 ('word^="ppa"', False),
                 ('word$="les"', True),
                 ('word$="s"', True),
                 ('2!=3', True),
                 ('2>1', True),
                 ('1<2', True),
                 ('1>2', False),
                 ('3<1', False),
                 ('1==1', True),
                 ('10>=10', True),
                 ('9.9<=10', True),
                 ('foo.a==10', True),
                 ('foo.a=="a"', False),
                 ('foo.a==\'a\'', False),
                 ('3*2>5', True),
                 ('2 gt 1', True),
                 ('1 lt 2', True),
                 ('1 gt 2', False),
                 ('3 lt 1', False),
                 ('10 gte 10', True),
                 ('9.9 lte 10', True),
                 ('3*2 gt 5', True),
                 ('None', None),
                 ('True', True),
                 ('False', False),
                 ('yes', True),
                 ('no', False),
                 ('int:"3"', 3),
                 ('str:50', "50"),
                 ('float:"2.5"', 2.5),
                 ('bool:"test"', True),
                 ('bool:1', True),
                 ('bool:""', False),
                 ('isint:5', True),
                 ('isint:"5"', False),
                 ('isnumber:2', True),
                 ('isnumber:2.5', True),
                 ('isnumber:"a"', False),
                 ('isfloat:1.0', True),
                 ('isfloat:1', False),
                 ('isstr:1', False),
                 ('isstr:"a"', True),
                 ('isbool:True', True),
                 ('isbool:False', True),
                 ('isbool:(2+1)', False),
                 ('isbool:bool:1', True),
                 ('isbool:bool:0', True),
                 ('len:word', 6),
                 ('True and True', True),
                 ('False and False', False),
                 ('True or False', True),
                 ('False or False', False),
                 #('2>1 and word.-1=="s"', True),
                 ('word=="apples"', True),
                 ('1==2 or word=="apples"', True),
                 ("'a' in 'apples'", True),
                 ("'ppl' in 'apples'", True),
                 ("word.1==word.2", True),
                 ('word is word2', True),
                 ("'index.html' fnmatches '*.html'", True),
                 ("'foo/index.html' fnmatches '*.html'", True),
                 ("'index.html' fnmatches '*.py'", False),
                 ("'index.html' fnmatches '*.h??l'", True),
                 ("'hello, world' matches /.*world/", True),
                 ("'hello, will' matches /.*world/", False),
                 ("'hello, world' matches '.*world'", True),
                 ("'hello, will' matches '.*world'", False),
                 ("'inception' in foo['c']", True),
                 ("'inception' in (foo['c'])", True),
                 ("exists:foo", True),
                 ("exists:baz", True),
                 ("exists:asdfsadf", False),
                 ("missing:foo", False),
                 ("missing:nobodyherebutuschickens", True),
                 ("missing:yesterday", True),
                 ("missing:foo.bar.baz", True),
                 ("missing:andrew", True),
                 ("'1' instr [1,2,3,4]", True),
                 ("'5' instr [1,2,3,4]", False),
                 ("'1' not instr [1,2,3,4]", False),
                 ("'5' not instr [1,2,3,4]", True),
                 ("1 in None", False),
                 ("1 instr None", False),
                 ('a=1', {'a': 1}),
                 ('{"a":1}', {'a': 1}),
                 ('[1,2,3]', [1, 2, 3]),
                 ('[1,2,3,[4,5,6]]', [1, 2, 3, [4, 5, 6]]),
                 ('[1,2,3,[4,5,6,[7,8,9]]]', [1, 2, 3, [4, 5, 6, [7, 8, 9]]]),
                 ('[1]', [1]),
                 ('[]', []),
                 ("d:'5'", 5),
                 ("d:'5' + 1", 6),
                 ("d:'5' + d:'1'", 6),
                 ('debug:d:5', "d:'5'"),
                 ('filesize:1024', '1.0 KB'),
                 ('abs:-3.14', 3.14),
                 ('basename:"/foo/bar/baz"', "baz"),
                 ('bool:""', False),
                 ('capitalize:"hello"', 'Hello'),
                 ('ceil:3.14', 4),
                 ('choices:choicetest', []),
                 ('chain:[[1, 2], [3, 4]]', [1, 2, 3, 4]),
                 ('chr:65', 'A'),
                 ("collect:[['hello', 'world'], 0]", ['h', 'w']),
                 ("sorted:items:collectmap:[['hello', 'world'], 0]", [('h', 'hello'), ('w', 'world')]),
                 ("collectids:objects", [1, 2, 3]),
                 ("commalist:['hello', 'world']", "hello,world"),
                 ("commaspacelist:['hello', 'world']", "hello, world"),
                 ("'hello\\nworld'", "hello\nworld"),
                 (r"'you can \"quote me\" on that'", 'you can "quote me" on that'),
                 ("'\\\\'", "\\"),
                 ("'helloworld'[1]", 'e'),
                 ("'helloworld'[-1]", 'd'),
                 ("'helloworld'[:2]", "he"),
                 ("'helloworld'[2:4]", "ll"),
                 ("'helloworld'[::-1]", "dlrowolleh")
                 ]

        for expression, result in tests:
            print(expression, result)
            expression_result = c.eval(expression)
            print("\t", expression_result)
            self.assertEqual(expression_result, result)

    def test_expression_index(self):
        """Test the index operator"""
        c = Context()
        c['foo'] = {}
        c['baz'] = 2
        c['foo.a'] = 10
        c['foo.b'] = 20
        c['foo.c'] = dict(inception="three levels")
        c['word'] = 'apples'
        c['word2'] = c['word']
        c['lt'] = "less than"

        class Obj(object):
            def __init__(self):
                self.n = 123
                self.foo = ["Hello", "World", "!"]
        c['o'] = Obj()

        tests = [('"apples"[0]', 'a'),
                 ('"apples"[1]', 'p'),
                 ('"apples"[1+2]', 'l'),
                 ('"apples"[-1]', 's'),
                 ('foo["a"]', 10),
                 ('foo["b"]', 20),
                 ('foo["c"]', dict(inception="three levels")),
                 ('foo["c"]["inception"]', "three levels"),
                 ('foo.c["inception"]', "three levels"),
                 ('foo.c["inception"][1]', "h"),
                 ('o["n"]', 123),
                 ('o["foo"][1]', "World"),
                 ]

        for expression, result in tests:
            print(expression)
            expression_result = c.eval(expression)
            self.assertEqual(expression_result, result)
            #expression_result_callable = c.compile(expression)
            #self.assertEqual(expression_result_callable(), result)

    def test_expression_filter(self):
        """Test filter evaluation"""
        c = Context()
        c['filter'] = dict(double=lambda v: v * 2,
                           square=lambda v: v * v)
        c['data'] = dict(a=1, b=10, c=123)

        tests = [("3|filter.double", 6),
                 ("3|.filter.double", 6),
                 ("data.a + data.b|filter.double", 22),
                 ("(data.a + data.b)|filter.double", 22),
                 ("3|filter.square", 9),
                 ("3|filter.double|filter.square", 36),
                 ]

        for expression, result in tests:
            print(expression)
            expression_result = c.eval(expression)
            self.assertEqual(expression_result, result)
            #expression_result_callable = c.compile(expression)
            #self.assertEqual(expression_result_callable(), result)

    def test_expressions_with_fame(self):
        """Test expression evaluation in a frame"""
        c = Context()
        c['foo'] = dict(a=1, b=2, bar="apples")
        c['top'] = 10
        c['r'] = list(range(10))
        tests = [("a+b", 3),
                 (".top", 10),
                 ("a+.top", 11),
                 (".r.4+.top", 14)]
        with c.frame('foo'):
            for expression, result in tests:
                self.assertEqual(c.eval(expression), result)

    def test_set_lazy(self):
        """Test lazy evaluation"""
        c = Context()
        evaluations = [0]
        def add(a, b):
            evaluations[0] += 1
            return a + b
        c.set_lazy('foo', add, 3, 4)
        self.assertEqual(evaluations[0], 0)
        self.assertEqual(c['foo'], 7)
        self.assertEqual(evaluations[0], 1)
        self.assertEqual(c['foo'], 7)
        self.assertEqual(evaluations[0], 1)
        c.set_lazy('bar', lambda:{})
        self.assertEqual(c['bar'], {})

    def test_set_async(self):
        """Test asyncronous evaluation"""
        c = Context()
        c.set_async('foo', lambda:'bar')
        self.assertEqual(c['foo'], 'bar')
        self.assertEqual(c['foo'], 'bar')
        def waiter(wait_time, result):
            import time
            time.sleep(wait_time)
            return result
        c.set_async('bestthings', waiter, .1, 'guiness')
        self.assertEqual(c['bestthings'], 'guiness')
        self.assertEqual(c['bestthings'], 'guiness')

    def test_set_new(self):
        """Test setting values if not present"""
        c = Context()
        c.set_new('foo', {})
        self.assertEqual(c['foo'], {})
        c.set_new('foo', 100)
        self.assertEqual(c['foo'], {})

    def test_deleting(self):
        """Test deleting from context"""
        c = Context()
        c['foo'] = {}
        c['foo.bar'] = 1
        c['foo.baz'] = 2
        self.assert_('foo' in c)
        self.assert_('foo.bar' in c)
        self.assert_('foo.baz' in c)
        del c['foo.bar']
        self.assert_('foo' in c)
        self.assert_('foo.bar' not in c)
        self.assert_('foo.baz' in c)
        del c['foo']
        self.assert_('foo' not in c)
        self.assert_('foo.bar' not in c)
        self.assert_('foo.baz' not in c)

    def test_copy_move(self):
        """Test copying and moving values"""
        c = Context()
        c['foo'] = 123
        c['bar'] = {}
        c['bar.baz'] = 456
        c.copy('foo', 'foo2')
        self.assertEqual(c['foo'], 123)
        self.assertEqual(c['foo2'], 123)
        with c.frame('bar'):
            c.copy('baz', '.zab')
        self.assertEqual(c['zab'], 456)
        c = Context()
        c['foo'] = 123
        c['bar'] = {}
        self.assert_('foo' in c)
        c.move('foo', 'bar.foo')
        self.assert_('foo' not in c)
        self.assert_('bar.foo' in c)
        self.assertEqual(c['bar.foo'], 123)

    def test_scope(self):
        """Test scope facility"""
        c = Context()
        c['foo'] = dict(a=1, b=2)
        c['bar'] = {}
        c.push_frame('.foo')
        self.assertEqual(c['a'], 1)
        self.assertEqual(c['b'], 2)
        self.assert_('c' not in c)
        c.push_scope('.bar')
        c['.bar.c'] = 3
        self.assert_('c' in c)
        self.assertEqual(c['c'], 3)
        c.pop_scope()
        self.assert_('c' not in c)
        self.assertEqual(c['a'], 1)
        self.assertEqual(c['b'], 2)

    def test_stack(self):
        c = Context()

        c.push_stack('content', 'foo')
        self.assertEqual(c['.content'], 'foo')
        c.push_stack('content', 'bar')
        self.assertEqual(c['.content'], 'bar')
        value = c.pop_stack('content')
        self.assertEqual(value, 'bar')
        self.assertEqual(c['.content'], 'foo')
        value = c.pop_stack('content')
        self.assertEqual(value, 'foo')
        self.assert_(c['.content'] is None)
