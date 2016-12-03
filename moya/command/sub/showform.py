from __future__ import print_function
from __future__ import unicode_literals

import logging
import sys
from os.path import abspath, dirname
from urllib import urlencode, quote
import webbrowser

from fs.opener import open_fs

from ...context import Context
from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...compat import socketserver
from ...compat import PY2

if PY2:
    from thread import interrupt_main
else:
    from _thread import interrupt_main

from wsgiref.simple_server import (WSGIServer,
                                   WSGIRequestHandler,
                                   make_server)

log = logging.getLogger('moya.runtime')


class RequestHandler(WSGIRequestHandler):

    # Disable simple_server's logging to stdout
    def log_message(self, format, *args):
        pass


class ThreadedWSGIServer(socketserver.ThreadingMixIn, WSGIServer):
    daemon_threads = True


class Showform(SubCommand):
    """Show a form from the project"""
    help = "show a form from the project"

    def add_arguments(self, parser):
        parser.add_argument(dest="formelement", metavar="ELEMENTREF",
                            help="form element reference")
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", '--ini', dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to project settings file")
        parser.add_argument("-s", "--server", dest="server", default="main", metavar="SERVERREF",
                            help="server element to use")
        parser.add_argument("-H", "--host", dest="host", default="127.0.0.1",
                            help="IP address to bind to")
        parser.add_argument("-p", "--port", dest="port", default="8001",
                            help="port to listen on")
        parser.add_argument('-d', '--develop', dest="develop", action="store_true", default=False,
                            help="enable develop mode for debugging Moya server")
        return parser

    @classmethod
    def _post_build(cls, application):
        lib = application.archive.load_library_from_module(
            'moya.libs.showform',
            priority=100,
            template_priority=100
        )
        application.archive.build_libs()
        context = Context()
        application.archive.call(
            'moya.showform#install',
            context,
            '__showform__',
            server=application.server
        )

    def run(self):
        super(Showform, self).run()
        args = self.args

        application = WSGIApplication(
            self.location,
            self.get_settings(),
            args.server,
            validate_db=False,
            develop=self.args.develop,
            post_build_hook=self._post_build,
        )

        form_app, form = application.archive.get_element(args.formelement)

        log.info('testing {form} in {form_app}'.format(form=form, form_app=form_app))

        server = make_server(
            args.host,
            int(args.port),
            application,
            server_class=ThreadedWSGIServer,
            handler_class=RequestHandler
        )

        def handle_error(request, client_address):
            _type, value, tb = sys.exc_info()
            if isinstance(value, KeyboardInterrupt):
                interrupt_main()
        # Allow keyboard interrupts in threads to propagate
        server.handle_error = handle_error
        formelement_quoted = quote(args.formelement)

        url = "http://{}:{}/moya-show-form/form/{}/".format(args.host, args.port, formelement_quoted)
        log.info("opening %s", url)
        webbrowser.open(url)
        try:
            server.serve_forever()
        finally:
            log.debug('user exit')
            application.close()
