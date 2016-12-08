import unittest
import os

from fs.opener import open_fs

from moya.context import Context
from moya.console import Console
from moya.archive import Archive


class TestCalls(unittest.TestCase):

    def setUp(self):
        self.called = False
        path = os.path.abspath(os.path.dirname(__file__))
        self.fs = open_fs(path)
        self.context = Context()
        self.context['console'] = Console()
        self.archive = Archive()
        import_fs = self.fs.opendir("archivetest")
        self.archive.load_library(import_fs)
        self.archive.finalize()

    def test_moya_call_no_lazy(self):
        """Test moya call without lazy attribute"""
        self.archive('moya.tests#test_moya_call_no_lazy', self.context, None)
        self.assert_(self.context.root['called'])
        self.assertEqual(self.context['.result'], 123)

    def test_moya_call_lazy(self):
        """Test lazy moya calls"""
        self.archive('moya.tests#test_moya_call_lazy', self.context, None)
        self.assert_('called' not in self.context.root)
        self.assertEqual(self.context['result'], 123)
        self.assert_('called' in self.context.root)
        self.assert_(self.context.root['called'])

    # def test_call_no_lazy(self):
    #     """Test callable call without lazy attribute"""
    #     def callable(a, b):
    #         return a + b
    #     self.archive('moya.tests#test_call_no_lazy',
    #                  self.context,
    #                  callable=callable,
    #                  a=100,
    #                  b=23)
    #     self.assertEqual(self.context['.result'], 123)

    # def test_call_lazy(self):
    #     """Test callable call without lazy attribute"""
    #     def callable(a, b):
    #         self.called = True
    #         return a + b
    #     # Sanity check that there has been no call
    #     self.assert_('result' not in self.context)
    #     # Call callable lazily store the result in context
    #     self.archive('moya.tests#test_call_lazy',
    #                  self.context,
    #                  callable=callable,
    #                  a=100,
    #                  b=23)
    #     # Check callble has not been called yet
    #     self.assert_(not self.called)
    #     # Check lazy result is in context
    #     self.assert_('result' in self.context)
    #     # Check lazy callable still hasn't been called
    #     self.assert_(not self.called)
    #     # Check return value (should call callable)
    #     self.assertEqual(self.context['.result'], 123)
    #     # Check callable has been called
    #     self.assert_(self.called)
    #     # Check cached result
    #     self.assertEqual(self.context['.result'], 123)
