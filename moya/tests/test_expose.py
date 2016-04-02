from __future__ import unicode_literals
from __future__ import print_function


import unittest
import os

from moya import db
from moya import pilot
from moya.wsgi import WSGIApplication
from moya.console import Console
from moya.context import Context
from moya.context.tools import set_dynamic


class TestExpose(unittest.TestCase):
    """Test exposed Python code in a project."""

    def setUp(self):
        _path = os.path.abspath(os.path.dirname(__file__))
        path = os.path.join(_path, 'testproject')
        self.application = WSGIApplication(path,
                                           'settings.ini',
                                           strict=True,
                                           validate_db=False,
                                           disable_autoreload=True)
        console = Console()
        self.archive = self.application.archive
        db.sync_all(self.archive, console)
        self.context = context = Context()

        self.archive.populate_context(context)
        self.application.populate_context(context)
        set_dynamic(context)
        context['.console'] = console

    def tearDown(self):
        del self.archive
        del self.application

    def test_macros(self):
        app = self.archive.apps['site']

        self.assertEqual(6, self.archive("macro.expose.double", self.context, app, n=3))
        self.assertEqual(21, self.archive("macro.expose.tripple", self.context, app, n=7))

    def test_filters(self):
        app = self.archive.apps['site']
        self.context['.app'] = app
        with pilot.manage(self.context):
            self.assertEqual(1000, self.context.eval("10|'cube'"))
            self.assertEqual(1000, self.context.eval("10|'cube from site'"))
            self.assertEqual(1000, self.context.eval("10|.app.filters.cube"))
