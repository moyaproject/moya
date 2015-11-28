from __future__ import unicode_literals
from __future__ import print_function

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...console import Cell

import sys


class Libs(SubCommand):
    """List libraries installed in the project"""
    help = "get library information"

    def add_arguments(self, parser):
        parser.add_argument("-l", '--location', dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to projects settings file")
        parser.add_argument('--org', dest="org", default=None, metavar="ORGANIZATION",
                            help="show only libraries with from a specific organization")
        parser.add_argument('-f', '--freeze', dest="freeze", action="store_true",
                            help="output project library requirements")
        return parser

    def run(self):
        args = self.args
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      disable_autoreload=True,
                                      master_settings=self.master_settings)
        archive = application.archive
        table = []
        if args.org:
            prefix = args.org.lstrip('.') + '.'
        else:
            prefix = None

        libs = sorted(archive.libs.values(), key=lambda lib: lib.long_name)
        if prefix is not None:
            libs = [lib for lib in libs if lib.long_name.startswith(prefix)]

        if args.freeze:
            lib_freeze = "\n".join("{}=={}".format(lib.long_name, lib.version) for lib in libs) + '\n'
            sys.stdout.write(lib_freeze)
            return 0

        for lib in libs:
            name = lib.long_name
            if prefix is not None and not name.startswith(prefix):
                continue
            table.append([
                         name,
                         Cell(lib.version, bold=True, fg="magenta"),
                         Cell(lib.install_location, bold=True, fg="blue"),
                         ])
        self.console.table(table, header_row=['lib', 'version', 'location'])
