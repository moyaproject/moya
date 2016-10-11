from __future__ import unicode_literals

import logging
import sys
import os.path
from os.path import join as pathjoin
from wsgiref.simple_server import (WSGIServer,
                                   WSGIRequestHandler,
                                   make_server)

from fs.opener import open_fs

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...loggingconf import init_logging
from ...compat import PY2, socketserver

if PY2:
    from thread import interrupt_main
else:
    from _thread import interrupt_main

log = logging.getLogger('moya.runtime')


class ThreadedWSGIServer(socketserver.ThreadingMixIn, WSGIServer):
    daemon_threads = True


class RequestHandler(WSGIRequestHandler):

    # Disable simple_server's logging to stdout
    def log_message(self, format, *args):
        pass


class Serve(SubCommand):
    """Serve static files with moya.static"""
    help = "serve static files"

    def add_arguments(self, parser):
        parser.add_argument(dest="fs", metavar="PATH",
                            help="Path to serve")
        parser.add_argument('--host', dest='host', default='127.0.0.1',
                            help="server host")
        parser.add_argument('-p', '--port', default='8000',
                            help="server port")
        parser.add_argument('-t', '--templates', dest="serve_templates", action="store_true",
                            help="render and serve .html files as moya templates")
        parser.add_argument('--develop', dest="develop", action="store_true",
                            help="enable develop mode (to track down Python errors)")
        parser.add_argument('-a', '--show-access', action="store_true",
                            help="show access (permission) information")
        parser.add_argument('-d', '--show-dot', action="store_true",
                            help="do not hide dot files (beginning with a period)")

    def run(self):
        args = self.args
        fs = open_fs(args.fs)

        from ...command.sub import project_serve
        location = os.path.dirname(project_serve.__file__)

        init_logging(pathjoin(location, 'logging.ini'))

        if args.serve_templates:
            ini = 'templatesettings.ini'
        else:
            ini = 'settings.ini'

        application = WSGIApplication(
            location, ini, 'main', disable_autoreload=True, develop=args.develop)
        application.archive.filesystems['static'] = fs
        static_app = application.archive.apps['static']
        static_app.settings['show_permissions'] = args.show_access
        if args.show_dot:
            static_app.settings['hide'] = ''

        server = make_server(args.host,
                             int(args.port),
                             application,
                             server_class=ThreadedWSGIServer,
                             handler_class=RequestHandler)
        log.info("server started on http://{}:{}".format(args.host, args.port))

        def handle_error(request, client_address):
            _type, value, tb = sys.exc_info()
            if isinstance(value, KeyboardInterrupt):
                interrupt_main()
        server.handle_error = handle_error

        try:
            server.serve_forever()
        finally:
            application.close()
