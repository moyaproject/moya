from __future__ import unicode_literals
from __future__ import print_function

from ...command import SubCommand


import os


class WorkHere(SubCommand):
    """
    Set the default project location, by setting MOYA_PROJECT environment variable

    """
    help = "set default project location"

    def add_arguments(self, parser):
        parser.add_argument('-r', '--reset', dest="reset", action="store_true",
                            help="reset currently active project")

    def run(self):
        args = self.args
        if args.reset:
            project_dir = ''
        else:
            project_dir = os.path.abspath(os.getcwd())
        os.environ['MOYA_PROJECT'] = project_dir
