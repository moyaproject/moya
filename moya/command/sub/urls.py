from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...console import ConsoleHighlighter
from ...tools import url_join
from ...http import StatusCode


class URLHighlight(ConsoleHighlighter):
    styles = {
        None: "bold blue",
        "asterix": "bold yellow",
        "param": "bold magenta"
    }

    highlights = [
        r'(?P<param>\{.*?\})',
        r'(?P<asterix>\*)',
    ]


class TargetHighlight(ConsoleHighlighter):
    styles = {
        "lib": "bold blue",
        "name": "bold green",
        "hash": "white"
    }

    highlights = [
        r'(?P<lib>.*?)(?P<hash>#)(?P<name>.*?)[,\s$]',
    ]


class URLS(SubCommand):
    """List URLs"""
    help = "list URLs"

    def add_arguments(self, parser):
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to project settings file")
        parser.add_argument("--server", dest="server", default="main", metavar="SERVERREF",
                            help="server element to use")
        parser.add_argument("--sort", "-s", dest="sort", default=False, action="store_true",
                            help="sort URL output")
        parser.add_argument('-m', '--method', dest="method", default=None, metavar="VERB",
                            help="only show urls for the given method")
        parser.add_argument('-a', '--app', dest="app", metavar="APPLICATION", default=None,
                            help="only show urls for given app")
        parser.add_argument('--handler', default=None, metavar="STATUS",
                            help="show handlers for the given error")

    def run(self):
        args = self.args

        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      args.server,
                                      disable_autoreload=True,
                                      master_settings=self.master_settings)
        urlmapper = application.server.urlmapper
        urls = []

        def render_urlmapper(app_name, parent_url, urlmapper):
            for route in urlmapper.routes:
                if route.partial:
                    render_urlmapper(app_name, url_join(parent_url, route.route), route.target)
                else:
                    if args.handler:
                        handler = StatusCode(args.handler)
                        if handler not in route.handlers:
                            continue
                    else:
                        if args.method and not route.match_method(args.method, None):
                            continue
                        if route.handlers:
                            continue
                        if args.app and args.app != app_name:
                            continue
                    urls.append((
                                ", ".join(route.methods or ['*']),
                                url_join(parent_url, route.route),
                                app_name,
                                route.name or '',
                                ", ".join(route.target)))

        for route in urlmapper.routes:
            app_name = route.name or ''
            render_urlmapper(app_name, route.route, route.target)

        if args.sort:
            urls.sort(key=lambda row: row[1])

        def highlight_url(text):
            return URLHighlight.highlight(text)

        def highlight_target(text):
            return TargetHighlight.highlight(text)

        self.console.table(urls,
                           ["method(s)", "URL", "app", "name", "target(s)"],
                           cell_processors={1: highlight_url, 4: highlight_target})
