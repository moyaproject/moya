from __future__ import unicode_literals

from .. import logic
from .. import namespaces
from ..tools import match_exception
from ..elements.elementbase import LogicElement, Attribute
from ..tags.context import DataSetter
from ..request import MoyaRequest
from ..context import Context
from ..compat import text_type, urlparse, parse_qs, urlencode

import sys
import io

import logging
log = logging.getLogger('moya.tests')


class Suite(LogicElement):
    """A suite of unit tests"""

    class Help:
        synopsis = "define a suite of test cases"

    xmlns = namespaces.test
    description = Attribute("Short description of test suite", map_to="_description", required=True)
    slow = Attribute("Are these tests slow to run?", type="boolean", default=False, map_to="_slow")
    group = Attribute("Test group", default=None, map_to="_group")

    def finalize(self, context):
        self.description = self._description(context)
        self.slow = self._slow(context)
        self.group = self._group(context)


def make_mock_request(method, url, environ=None, query=None, default_environ=True, update_environ=None):
    """Mock a request object for testing"""
    parsed_url = urlparse(url)

    request_query = parse_qs(parsed_url.query)
    if query is not None:
        request_query.update(query)
    qs = urlencode(request_query)

    body_file = io.BytesIO(b'')

    if default_environ:
        request_environ = {
            b"REQUEST_METHOD": method,
            b"SCRIPT_NAME": b"",
            b"PATH_INFO": parsed_url.path,
            b"QUERY_STRING": qs,
            b"CONTENT_TYPE": b"text/plain",
            b"SERVER_NAME": b"",
            b"SERVER_PORT": b"",
            b"SERVER_PROTOCOL": b"HTTP/1.1",

            b"wsgi.version": (1, 0),
            b"wsgi.url_scheme": parsed_url.scheme,
            b"wsgi.input": body_file,
            b"wsgi.errors": sys.stderr,
            b"wsgi.multithread": True,
            b"wsgi.multiprocess": True,
            b"wsgi.run_once": False,
        }
    else:
        request_environ = {}
    if environ is not None:
        request_environ.update(environ)
    if update_environ is not None:
        request_environ.update(update_environ)

    # WSGI requires bytes not unicode
    encoded_environ = {}
    for k, v in request_environ.items():
        if isinstance(k, text_type):
            k = k.encode('utf-8', 'replace')
        if isinstance(v, text_type):
            v = v.encode('utf-8', 'replace')
        encoded_environ[k] = v

    request = MoyaRequest(encoded_environ)
    return request


class Request(DataSetter):
    """Create a mock request"""

    class Help:
        synopsis = "make a mock request"

    xmlns = namespaces.test
    url = Attribute("URL for request", default="/")
    query = Attribute("Query data", type="expression", default=None)
    method = Attribute("Request method", choices=["GET", "POST", "HEAD", "PUT"], default="GET")
    environ = Attribute("WSGI environment", type="expression", default=None)
    default_environ = Attribute("build a default WSGI environ?", type="boolean", default=True)

    def logic(self, context):
        params = self.get_parameters(context)
        let_map = self.get_let_map(context)

        request = make_mock_request(params.method,
                                    params.url,
                                    environ=params.environ,
                                    query=params.query,
                                    default_environ=params.default_environ,
                                    update_environ=let_map)

        self.set_context(context,
                         params.dst,
                         request)


class LoadProject(DataSetter):
    """Load a moya project"""
    xmlns = namespaces.test

    class Help:
        synopsis = "load a project for testing"

    location = Attribute('Project location (relative to library)', default="./testproject")
    settings = Attribute('Settings path within project', default="settings.ini")
    server = Attribute('Server name', default="main")
    dst = Attribute('Destination', type="reference", default=".project")

    def logic(self, context):
        from .. import wsgi
        params = self.get_parameters(context)
        project_fs = self.lib.load_fs.opendir(params.location)
        application = wsgi.WSGIApplication(project_fs,
                                           params.settings,
                                           params.server,
                                           disable_autoreload=True)
        self.set_context(context, params.dst, application)


class GetResponse(DataSetter):
    xmlns = namespaces.test

    class Help:
        synopsis = "get a test response"

    project = Attribute('Request object', type="reference", default=".project")
    request = Attribute('request object', type="reference", default="request")
    dst = Attribute('Destination', type="reference", default="response")

    def logic(self, context):
        params = self.get_parameters(context)
        project = context[params.project]
        request = context[params.request]
        project_context = Context()
        response = project.get_response(request, project_context)
        self.set_context(context, params.dst, response)


class SetUp(LogicElement):
    """Logic to set up unit tests. Must be inside a <suite>"""
    xmlns = namespaces.test

    class Help:
        synopsis = "setup code for a test suite"


class TearDown(LogicElement):
    """Logic to tear down a unit test suite. Must be inside a <suite>"""
    xmlns = namespaces.test

    class Help:
        synopsis = "tear down (finalize) code for a test suite"


class Case(LogicElement):
    """A unit test inside a <suite>"""

    class Help:
        synopsis = "define a test case"

    xmlns = namespaces.test
    description = Attribute("Short description of test suite")
    slow = Attribute("Is this test slow?", type="boolean", default=False)

    def finalize(self, context):
        self.description = self.description(context)


class Fail(LogicElement):
    """Note a failed test"""
    xmlns = namespaces.test

    class Help:
        synopsis = "fail a test case"

    def logic(self, context):
        text = self.text
        try:
            text = context.sub(text)
        except:
            # ultra-cautious so as not break unit tests
            pass
        context['._test_results'].add_fail(self, text)
        if context.get('._test_runner.break', False):
            raise logic.DebugBreak(self, exit=True)
        raise logic.EndLogic('fail')


class Require(LogicElement):
    """Check code throws an exception"""
    xmlns = namespaces.test

    class Help:
        synopsis = "require an exception to be thrown in a test case"

    class Meta:
        trap_exceptions = True

    exception = Attribute("Type of exception to catch", type="text", default="*")

    def on_exception(self, context, moya_exception):
        exception = self.exception(context)
        if not match_exception(moya_exception.type, exception):
            context['._test_results'].add_fail(self, "exception '{}' not thrown".format(exception))

    def logic(self, context):
        yield logic.DeferNodeContents(self)
        raise logic.EndLogic('fail')
