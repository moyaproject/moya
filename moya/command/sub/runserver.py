from __future__ import unicode_literals
from __future__ import print_function

import sys
import logging

from wsgiref.simple_server import (WSGIServer,
                                   WSGIRequestHandler,
                                   make_server)

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...compat import socketserver
from ...compat import PY2


if PY2:
    from thread import interrupt_main
else:
    from _thread import interrupt_main

log = logging.getLogger('moya.runtime')


# import gc
# gc.set_debug(gc.DEBUG_LEAK)


class RequestHandler(WSGIRequestHandler):

    # Disable simple_server's logging to stdout
    def log_message(self, format, *args):
        pass


class ThreadedWSGIServer(socketserver.ThreadingMixIn, WSGIServer):
    daemon_threads = True


class ForkingWSGIServer(socketserver.ForkingMixIn, WSGIServer):
    pass


class Runserver(SubCommand):
    """Run a local Moya development server"""
    help = "run a development server"

    def add_arguments(self, parser):
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", '--ini', dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to project settings file")
        parser.add_argument("-s", "--server", dest="server", default="main", metavar="SERVERREF",
                            help="server element to use")
        parser.add_argument("-H", "--host", dest="host", default="127.0.0.1",
                            help="IP address to bind to")
        parser.add_argument("-p", "--port", dest="port", default="8000",
                            help="port to listen on")
        parser.add_argument("-b", "--breakpoint", dest="breakpoint", action="store_true", default=False,
                            help="enter debug mode on every view")
        parser.add_argument("--no-validate", dest="novalidate", action="store_true", default=False,
                            help="don't validate database models before running server")
        parser.add_argument("--breakpoint-startup", dest="breakpoint_startup", action="store_true", default=False,
                            help="debug startup process")
        parser.add_argument("--no-reload", dest="noreload", action="store_true", default=False,
                            help="disable auto-reload")
        parser.add_argument("--slow", dest="slow", action="store_true", default=False,
                            help="simulate network latency by inserting delays")
        parser.add_argument("--strict", dest='strict', action="store_true", default=False,
                            help="enable 'strict' checking of tag attributes")
        parser.add_argument("-t", "--use-threads", dest='usethreads', action="store_true", default=False,
                            help='enable multi-threaded server')
        parser.add_argument('-d', '--develop', dest="develop", action="store_true", default=False,
                            help="enable develop mode for debugging Moya server")

        # TODO: better forking dev server
        # Disabled because the default implementation doesn't use process pooling,
        # which prevents Moya from caching anything in memory

        # parser.add_argument('--enable-forking', dest='usefork', action="store_true",
        #                     help='enable forking server')
        return parser

    def run(self):
        super(Runserver, self).run()
        args = self.args

        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      args.server,
                                      breakpoint=args.breakpoint,
                                      breakpoint_startup=args.breakpoint_startup,
                                      validate_db=not args.novalidate,
                                      disable_autoreload=self.args.noreload,
                                      simulate_slow_network=self.args.slow,
                                      strict=self.args.strict,
                                      develop=self.args.develop)
        application.preflight()

        try:

            server_class = WSGIServer
            if args.usethreads:
                server_class = ThreadedWSGIServer
                log.info('using multi threaded server')
            # elif args.usefork:
            #     server_class = ForkingWSGIServer
            #     log.info('using forking server')

            server = make_server(args.host,
                                 int(args.port),
                                 application,
                                 server_class=server_class,
                                 handler_class=RequestHandler)
        except IOError as e:
            # 98 on Linux, 48 on OSX?
            if e.errno in (48, 98):
                log.critical("couldn't run moya server, another process may be running on port %s", args.port)
            raise

        if self.args.slow:
            log.info('network latency simulation is enabled')
        log.info("development server started on http://{}:{}".format(args.host, args.port))

        def handle_error(request, client_address):
            _type, value, tb = sys.exc_info()
            if isinstance(value, KeyboardInterrupt):
                interrupt_main()
        # Allow keyboard interrupts in threads to propagate
        server.handle_error = handle_error

        try:
            server.serve_forever()
        finally:
            log.debug('user exit')
            application.close()

            # del server
            # del application
            # import gc
            # gc.collect()

            # import objgraph
            # objgraph.show_most_common_types(limit=200)


        # Can track down memory leaks

        # del server
        # del application
        #
        # from moya.elements.registry import default_registry
        # default_registry.clear()
        # import gc
        # gc.collect()
        #

        # import objgraph
        # objgraph.show_most_common_types(limit=20)
        #
        # contexts= objgraph.by_type('moya.context.context.Context')
        # print([id(c) for c in contexts])
        # obj = objgraph.by_type('Context')[-1]
        # print(repr(obj))
        # objgraph.show_backrefs([obj], max_depth=3, refcounts=True, filename="refs.png")
