from __future__ import unicode_literals

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...compat import text_type, raw_input

try:
    import readline
except ImportError:
    pass


class Trace(SubCommand):
    """URL tools"""
    help = "URL tools"

    def add_arguments(self, parser):
        parser.add_argument(dest="url", default=None, metavar="URL",
                            help="display the moya code that may be invoked by URL")
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument('-m', '--method', dest="method", default="GET", metavar="VERB",
                            help="Method of URL (GET, POST etc)")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to project settings file")
        parser.add_argument("--server", dest="server", default="main", metavar="SERVERREF",
                            help="server element to use")
        parser.add_argument('--step', dest="step", action="store_true",
                            help="step through each point in the trace")

    def run(self):
        args = self.args
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      args.server,
                                      disable_autoreload=True,
                                      master_settings=self.master_settings)

        count = 0
        for route_data, (app, element) in application.server.trace(application.archive,
                                                                   args.url,
                                                                   args.method):
            count += 1
            self.console.div()
            self.console("In file ")("\"%s\"" % element._location).nl()
            self.console.table(sorted(route_data.items()), header=False, dividers=False)
            self.console.xmlsnippet(element._code, element.source_line or 0, extralines=3)
            if args.step:
                raw_input()

        self.console.nl()("{} {}".format(args.method, args.url), bold=True, fg="magenta" if args.method == "GET" else "blue")(" maps to ")(text_type(count), bold=True)(" target(s)").nl()
