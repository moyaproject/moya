from __future__ import unicode_literals
from __future__ import print_function

import argparse
import os
import sys
import io
import glob

from moya.compat import text_type
from moya.settings import SettingsContainer
from moya.console import Console

DEFAULT_HOME_DIR = '/etc/moya/'


class CommandError(Exception):
    pass


class MoyaSrv(object):
    """Moya Service"""

    def get_argparse(self):
        parser = argparse.ArgumentParser(prog="moya-srv",
                                         description=self.__doc__)

        parser.add_argument('-d', '--debug', dest="debug", action="store_true",
                            help="enable debug information (show tracebacks)")
        parser.add_argument('--home', dest="home", metavar="PATH", default=None,
                            help="moya service directory")

        subparsers = parser.add_subparsers(title="available sub-commands",
                                           dest="subcommand",
                                           help="sub-command help")

        list_parser = subparsers.add_parser('list',
                                            help="list projects",
                                            description="list enabled projects")

        where_parser = subparsers.add_parser('where',
                                             help='find project directory',
                                             description="output the location of the project")

        where_parser.add_argument(dest="name", metavar="PROJECT",
                                  help="name of a project")

        return parser

    def error(self, msg, code=-1):
        sys.stderr.write(msg + '\n')
        sys.exit(code)

    def run(self):
        parser = self.get_argparse()
        self.args = args = parser.parse_args(sys.argv[1:])
        self.console = Console()

        self.home_dir = home_dir = args.home or os.environ.get('MOYA_SRV_HOME', None) or DEFAULT_HOME_DIR

        settings_path = os.path.join(home_dir, 'moya.conf')
        try:
            with io.open(settings_path, 'rt') as f:
                self.settings = SettingsContainer.read_from_file(f)
        except IOError:
            self.error('unable to read {}'.format(settings_path))
            return -1

        method_name = "run_" + args.subcommand.replace('-', '_')
        try:
            return getattr(self, method_name)() or 0
        except CommandError as e:
            self.error(text_type(e))
        except Exception as e:
            if args.debug:
                raise
            self.error(text_type(e))

    def _get_projects(self):
        project_paths = self.settings.get_list('projects', 'read')
        paths = []
        cwd = os.getcwd()
        try:
            os.chdir(self.home_dir)
            for path in project_paths:
                glob_paths = glob.glob(path)
                paths.extend([os.path.abspath(p) for p in glob_paths])
        finally:
            os.chdir(cwd)

        return paths

    def read_project(self, path):
        settings = SettingsContainer.read_os(path)
        return settings

    def run_list(self):
        table = []
        for path in self._get_projects():
            settings = self.read_project(path)
            location = settings.get('service', 'location', '?')
            name = settings.get('service', 'name', '?')
            domains = "\n".join(settings.get_list('service', 'domain(s)', ""))
            table.append([name, location, domains])
        self.console.table(table, header_row=['name', 'location', 'domains'])

    def run_where(self):
        name = self.args.name
        location = None
        for path in self._get_projects():
            settings = self.read_project(path)
            if settings.get('service', 'name', None) == name:
                location = settings.get('service', 'location', None)
        if location is None:
            return -1
        sys.stdout.write(location)


def main():
    moya_srv = MoyaSrv()
    sys.exit(moya_srv.run() or 0)
