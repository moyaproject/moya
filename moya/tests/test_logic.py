from __future__ import unicode_literals
from __future__ import print_function

import os.path
import unittest
from fs.opener import open_fs
from moya.context import Context
from moya.archive import Archive
from moya.console import Console

from moya.tags import context, config

BF_HELLO = """
++++++++[>++++[>++>+++>+++>+<<<<-]>+>+>->>+[<]<-]>>.>---.+++++++..+++.>>.<-.<.+++.------.--------.>>+.>++.
"""

class TestLogic(unittest.TestCase):

    def setUp(self):
        path = os.path.abspath(os.path.dirname(__file__))
        self.fs = open_fs(path)
        self.context = Context()
        self.context['console'] = Console()
        self.archive = Archive()
        import_fs = self.fs.opendir("archivetest")
        self.archive.load_library(import_fs)
        self.archive.finalize()

    def test_setcontext(self):
        """Test setting values in the context"""
        c = self.context
        setcontext = self.archive.get_callable('moya.tests#setcontext')
        setcontext(c)
        self.assertEqual(c['foo'], 1)
        self.assertEqual(c['bar.baz'], "Hello")
        self.assertEqual(c['half'], 0.5)
        self.assertEqual(c['bool'], True)
        self.assertEqual(c['t'], True)
        self.assertEqual(c['f'], False)
        self.assertEqual(c['n'], None)
        self.assertEqual(c['l'], [])
        self.assertEqual(c['j'], {"list": [1, 2, 3], "map": dict(foo=10, bar=20)})
        self.assertEqual(c['fruit'], ['apples', 'oranges', 'pears'])

    def test_setcontext_by_value(self):
        """Test setting values from the 'value' attribute"""
        #print self.archive.libs['moya.tests'].elements_by_name
        c = self.context
        self.archive('moya.tests#setcontextbyvalue', c, None)
        self.assertEqual(c['foo'], 10)
        self.assertEqual(c['bar'], 15)
        self.assertEqual(c['zero'], 0)
        self.assertEqual(c['empty'], '')
        self.assertEqual(c['fruit'], 'apple')
        self.assertEqual(c['grapes'], 'grapegrapegrape')
        self.assertEqual(c['nograpes'], "'grape'*3")
        self.assertEqual(c['pi'], 3.14)
        self.assertEqual(c['check'], True)
        self.assertEqual(c['check2'], False)
        self.assertEqual(c['s'], 27)

    def test_macro(self):
        """Test macro calling"""
        self.assertEqual(self.archive('moya.tests#macrotest1', self.context, None), 4)
        #self.assertEqual(self.context['.returned'], 4)
        self.assertEqual(self.archive('moya.tests#macroreturnlist', self.context, None), [1, 2, 3])
        self.assertEqual(self.archive('moya.tests#testscope1', self.context, None)['b'], 2)
        self.assertEqual(self.archive('moya.tests#nested', self.context, None, 5), 10)
        self.assertEqual(self.archive('moya.tests#quadruple', self.context, None, 3), 12)

    # def test_call(self):
    #     """Test calling Python functions"""
    #     class Obj(object):

    #         def method1(self):
    #             print "method 1 called!"
    #             return "method1 called"

    #         def method2(self, a, b):
    #             return a + b
    #     obj = Obj()

    #     self.assertEqual(self.archive('moya.tests#callabletest1', self.context, obj=obj),
    #                      "method1 called")

    #     self.assertEqual(self.archive('moya.tests#callabletest2', self.context, obj=obj),
    #                      20)

    def test_ifelse(self):
        """Test if / elif /else"""
        tests = [(1, "apple"),
                 (2, "orange"),
                 (3, "pear"),
                 (4, "not a fruit"),
                 (5, "not a fruit")]

        for n, correct in tests:
            result = self.archive('moya.tests#ifelse', self.context, None, n=n)
            self.assertEqual(result, correct)

    def test_bf(self):
        """Test BF macro"""
        # Just because is a moderately complex piece of code with lots of loops
        context = self.context
        call = self.archive.call
        result = call('moya.tests#bf', context, None, program=BF_HELLO)
        self.assertEqual(result, "Hello World!\n")
