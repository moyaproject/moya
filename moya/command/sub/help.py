from __future__ import unicode_literals

from ...wsgi import WSGIApplication
from ...command import SubCommand
from ...command.subcommand import NoProjectError
from ...archive import Archive


class Help(SubCommand):
    """Dynamically generated help"""
    help = """display dynamically generated help"""

    def add_arguments(self, parser):
        parser.add_argument(dest="tag", metavar="TAGNAME",
                            help="Name of tag to get help on, may include namespace e.g. {http://moyaproject.com}if")
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to projects settings file")
        parser.add_argument("--server", dest="server", default='main', metavar="SERVERREF",
                            help="server element to use")
        parser.add_argument('-o', '--output', dest="html", default=None, metavar="PATH",
                            help="write docs as html")
        return parser

    def run(self):
        args = self.args
        try:
            application = WSGIApplication(self.location,
                                          self.get_settings(),
                                          args.server)
            archive = application.archive
        except (ValueError, NoProjectError):
            archive = Archive()
            # Not in a project directory
            # Only built in tags will be available

        console = self.console
        if args.html is not None:
            from ...console import Console
            console = Console(html=True)

        from ...elements.help import help
        console.div()
        if not help(archive, console, args.tag):
            return -1

        if args.html is not None:
            from ... import consolehtml
            html = console.get_text()
            html = consolehtml.render_console_html(html)

            with open(args.html, 'wb') as f:
                f.write(html.encode('utf-8'))
