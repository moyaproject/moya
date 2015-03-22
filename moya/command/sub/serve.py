from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...loggingconf import init_logging
from ...compat import PY2

from fs.opener import fsopendir
import os.path
from os.path import join as pathjoin

import sys
from wsgiref.simple_server import WSGIRequestHandler, make_server


if PY2:
    from thread import interrupt_main
else:
    from _thread import interrupt_main


import logging
log = logging.getLogger('moya.runtime')


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

    def run(self):
        args = self.args
        fs = fsopendir(args.fs)

        from ...command.sub import project_serve
        location = os.path.dirname(project_serve.__file__)

        init_logging(pathjoin(location, 'logging.ini'))

        if args.serve_templates:
            ini = 'templatesettings.ini'
        else:
            ini = 'settings.ini'

        application = WSGIApplication(location, ini, 'main', disable_autoreload=True)
        application.archive.filesystems['static'] = fs

        server = make_server(args.host,
                             int(args.port),
                             application,
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
