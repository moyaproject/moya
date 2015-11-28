from __future__ import unicode_literals
from __future__ import print_function

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...console import Cell


class Apps(SubCommand):
    """List project applications"""
    help = "get application information"

    def add_arguments(self, parser):
        parser.add_argument("-l", '--location', dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to projects settings file")
        return parser

    def run(self):
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      disable_autoreload=True,
                                      master_settings=self.master_settings)
        archive = application.archive
        table = []

        for name, app in sorted(archive.apps.items()):
            table.append([
                         name,
                         app.lib.long_name,
                         Cell(app.lib.version, bold=True, fg="magenta"),
                         ])
        self.console.table(table,
                           ['app', 'lib', 'version'])
