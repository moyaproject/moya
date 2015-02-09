from __future__ import unicode_literals
from __future__ import print_function

from ...command import SubCommand
from ...wsgi import WSGIApplication

from wsgiref.simple_server import WSGIRequestHandler, make_server

import sys
import thread
import logging
log = logging.getLogger('moya.runtime')


class RequestHandler(WSGIRequestHandler):

    # Disable simple_server's logging to stdout
    def log_message(self, format, *args):
        pass


class Runserver(SubCommand):
    """Run a local Moya development server"""
    help = "run a development server"

    def add_arguments(self, parser):
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", '--ini', dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to project settings file")
        parser.add_argument("--server", dest="server", default="main", metavar="SERVERREF",
                            help="server element to use")
        parser.add_argument("-H", "--host", dest="host", default="127.0.0.1",
                            help="IP address to bind to")
        parser.add_argument("-p", "--port", dest="port", default="8000",
                            help="port to listen on")
        parser.add_argument("-b", "--breakpoint", dest="breakpoint", action="store_true", default=False,
                            help="enter debug mode on every view")
        parser.add_argument('--no-validate', dest="novalidate", action="store_true", default=False,
                            help="don't validate database models before running server")
        parser.add_argument('--breakpoint-startup', dest="breakpoint_startup", action="store_true", default=False,
                            help="debug startup process")
        return parser

    def run(self):
        super(Runserver, self).run()
        args = self.args
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      args.server,
                                      breakpoint=args.breakpoint,
                                      breakpoint_startup=args.breakpoint_startup,
                                      validate_db=not args.novalidate)
        application.preflight()

        server = make_server(args.host,
                             int(args.port),
                             application,
                             handler_class=RequestHandler)
        log.info("development server started on http://{}:{}".format(args.host, args.port))

        def handle_error(request, client_address):
            _type, value, tb = sys.exc_info()
            if isinstance(value, KeyboardInterrupt):
                thread.interrupt_main()
        # Allow keyboard interrupts in threads to propagate
        server.handle_error = handle_error

        try:
            server.serve_forever()
        finally:
            pass

            # del server
            # del application
            # from moya.elements.registry import default_registry
            # default_registry.clear()
            # import gc
            # gc.collect()

            # import objgraph
            # objgraph.show_most_common_types(limit=20)

            # obj = objgraph.by_type('Attribute')[0]
            # print(repr(obj))
            # objgraph.show_backrefs([obj], max_depth=2, refcounts=True, filename="refs.png")
