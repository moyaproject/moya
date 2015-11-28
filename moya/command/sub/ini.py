from __future__ import unicode_literals
from __future__ import print_function

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ... import iniparse

import sys


class Ini(SubCommand):
    """
    Display the INI settings that will be used by the project.

    """
    help = """display INI settings"""

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

        ini = iniparse.write(application.archive.cfg)
        self.console.ini(ini)
