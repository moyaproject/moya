from __future__ import unicode_literals
from __future__ import print_function

import unittest
import os

from moya import db
from moya.wsgi import WSGIApplication
from moya.console import Console
from moya.context import Context
from moya.context.tools import set_dynamic


class TestProject(unittest.TestCase):

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

        self.application.populate_context(context)
        set_dynamic(context)
        context['.console'] = console

    def tearDown(self):
        del self.archive
        del self.application

    def test_content(self):
        """Test content in a project"""
        app = self.archive.apps['site']
        html = self.archive('site#render_content', self.context, app, content="#content.tests.base")

        assert '[TESTS]' in html
        assert '<title>[TESTS]</title>' in html

        html = self.archive('site#render_content', self.context, app, content="#content.tests.merge.replace")
        assert "[MERGE TEST][B][END MERGE TEST]" in html

        html = self.archive('site#render_content', self.context, app, content="#content.tests.merge.append")
        assert "[MERGE TEST][A][B][END MERGE TEST]" in html

        html = self.archive('site#render_content', self.context, app, content="#content.tests.merge.prepend")
        assert "[MERGE TEST][B][A][END MERGE TEST]" in html

        html = self.archive('site#render_content', self.context, app, content="#content.tests.node", var="FOO")
        assert "TEMPLATE VAR FOO" in html
