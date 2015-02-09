from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...loggingconf import init_logging

from fs.path import dirname
from fs.opener import fsopendir
from os.path import join as pathjoin

import sys
import thread
from wsgiref.simple_server import WSGIRequestHandler, make_server


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
                            help="Path to Serve")
        parser.add_argument('--host', dest='host', default='127.0.0.1',
                            help="Host")
        parser.add_argument('-p', '--port', default='8000',
                            help="port")

    def run(self):
        args = self.args
        fs = fsopendir(args.fs)

        from ...command.sub import project_serve
        location = dirname(project_serve.__file__)

        init_logging(pathjoin(location, 'logging.ini'))
        application = WSGIApplication(location, 'settings.ini', 'main')
        application.archive.filesystems['static'] = fs

        server = make_server(args.host,
                             int(args.port),
                             application,
                             handler_class=RequestHandler)
        log.info("server started on http://{}:{}".format(args.host, args.port))

        def handle_error(request, client_address):
            _type, value, tb = sys.exc_info()
            if isinstance(value, KeyboardInterrupt):
                thread.interrupt_main()
        server.handle_error = handle_error
        server.serve_forever()
