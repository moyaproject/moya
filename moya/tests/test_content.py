import unittest
import os

from fs.opener import open_fs

from moya.context import Context
from moya.console import Console
from moya.archive import Archive
from moya.content import Content


class TestContent(unittest.TestCase):

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

    def test_content(self):
        value = self.archive('moya.tests#test_render_content', self.context, None)
        self.assertEqual(value, "<strong>bold</strong>")

        self.archive('moya.tests#test_render_content_2', self.context, None)
        self.assertEqual(self.context['.html'], "<em>emphasize</em>")

