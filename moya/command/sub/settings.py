from __future__ import unicode_literals

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...console import Cell


class Settings(SubCommand):
    """Manage moya project settings"""
    help = "manage settings"

    def add_arguments(self, parser):
        parser.add_argument(dest="name", default=None, metavar="NAME", nargs='?',
                            help="display settings for a specific library or application")
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to projects settings file")
        parser.add_argument("--server", dest="server", default='main', metavar="SERVERREF",
                            help="server element to use")
        return parser

    def run(self):
        args = self.args
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      args.server,
                                      disable_autoreload=True,
                                      master_settings=self.master_settings)
        archive = application.archive

        libstyle = dict(bold=True, fg="magenta")
        appstyle = dict(bold=True, fg="green")

        if args.name is not None:
            try:
                if '.' in args.name:
                    libs = [(args.name, archive.libs[args.name])]
                    apps = []
                else:
                    apps = [(args.name, archive.apps[args.name])]
                    libs = []
            except KeyError:
                self.console.error("'%s' is not an application or library in this project" % args.name)
                return -1
        else:
            libs = archive.libs.items()
            apps = archive.apps.items()

        for name, lib in sorted(libs):
            if lib.settings:
                self.console.nl()("[LIB] %s settings" % name, **libstyle).nl()
                table = []
                table.append([Cell("Setting", bold=True), Cell("Value", bold=True)])
                for k, v in lib.settings.items():
                    table.append([Cell(k), Cell(v)])
                self.console.table(table)

        for name, app in sorted(apps):
            if app.settings:
                self.console.nl()("[APP] %s: %s settings" % (app.lib.long_name, app.name), **appstyle).nl()

                table = []
                table.append([Cell("Setting", bold=True), Cell("Value", bold=True)])
                for k, v in app.settings.items():
                    table.append([Cell(k), Cell(v)])
                self.console.table(table)
