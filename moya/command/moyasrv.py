from __future__ import unicode_literals
from __future__ import print_function

import argparse
import os
import sys
import io
import glob
import tempfile

from moya.compat import text_type
from moya.settings import SettingsContainer
from moya.console import Console

DEFAULT_HOME_DIR = '/etc/moya/'


DEFAULT_CONF = """
[projects]
read = ./sites-enabled/*.ini
logging = logging.ini
"""

DEFAULT_LOGGING = """
# Logging conf for production
# Only errors and request information is written to stdout

[logger:root]
handlers=syslog

[logger:moya]
handlers=syslog
level=DEBUG
propagate=no

[logger:moya.startup]
level=INFO
handlers=syslog
propagate=no

[logger:moya.srv]
level=INFO
handlers=syslog
propagate=no

[logger:moya.request]
level=DEBUG
handlers=null
propagate=no

[handler:stdout]
class=StreamHandler
formatter=simple
args=(sys.stdout,)

[handler:syslog]
formatter = simple
class = moya.logtools.MoyaSysLogHandler

[formatter:simple]
format=:%(name)s:%(levelname)s: %(message)s
datefmt=[%d/%b/%Y %H:%M:%S]

[formatter:format_referer]
format=%(asctime)s %(message)s
datefmt=[%d/%b/%Y %H:%M:%S]

"""

BASH_TOOLS = r"""
moyacd () {
    cd $(moya-srv where $1)
}

alias moya-cd=moyacd
PS1="\`if [ \"\$MOYA_SERVICE_PROJECT\" != \"\" ]; then echo \"<\$MOYA_SERVICE_PROJECT>\"; fi\`$PS1"
export PS1
"""


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
        list_parser

        where_parser = subparsers.add_parser('where',
                                             help='find project directory',
                                             description="output the location of the project")

        where_parser.add_argument(dest="name", metavar="PROJECT",
                                  help="name of a project")

        restart_parser = subparsers.add_parser('restart',
                                               help='restart a project server',
                                               description="restart a server")

        restart_parser.add_argument(dest="name", metavar="PROJECT",
                                    help="name of a project")

        install_parser = subparsers.add_parser('install',
                                               help='install moya service',
                                               description="install moya service")

        install_parser.add_argument('--home', dest="home", metavar="PATH",
                                    default=DEFAULT_HOME_DIR,
                                    help="where to install service conf",)
        install_parser.add_argument('--force', dest="force", action="store_true",
                                    help="overwrite files that exist")

        install_parser

        return parser

    def error(self, msg, code=-1):
        sys.stderr.write(msg + '\n')
        sys.exit(code)

    def run(self):
        parser = self.get_argparse()
        self.args = args = parser.parse_args(sys.argv[1:])
        self.console = Console()

        if args.subcommand not in ['install']:
            self.home_dir = args.home or os.environ.get('MOYA_SERVICE_HOME', None) or DEFAULT_HOME_DIR
            settings_path = os.path.join(self.home_dir, 'moya.conf')
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

    def project_exists(self, name):
        for path in self._get_projects():
            settings = self.read_project(path)
            if settings.get('service', 'name', None) == name:
                return True
        return False

    def read_project(self, path):
        settings = SettingsContainer.read_os(path)
        return settings

    def run_list(self):
        table = []
        for path in self._get_projects():
            settings = self.read_project(path)
            location = settings.get('service', 'location', '?')
            name = settings.get('service', 'name', '?')
            domains = "\n".join(settings.get_list('service', 'domains', ""))
            table.append([name, domains, path, location])
        table.sort(key=lambda row: row[0].lower())
        self.console.table(table, header_row=['name', 'domain(s)', 'conf', 'location'])

    def run_where(self):
        name = self.args.name
        location = None
        for path in self._get_projects():
            settings = self.read_project(path)
            if settings.get('service', 'name', None) == name:
                location = settings.get('service', 'location', None)
        if location is None:
            self.error("no project '{}'".format(name))
            return -1
        sys.stdout.write(location)
        return 0

    def run_restart(self):
        name = self.args.name
        if not self.project_exists(name):
            self.error("no project '{}'".format(name))
        temp_dir = os.path.join(self.settings.get('service', 'temp_dir', tempfile.gettempdir()), 'moyasrv')
        try:
            os.makedirs(temp_dir)
        except OSError:
            pass
        change_path = os.path.join(temp_dir, "{}.changes".format(name))
        try:
            with open(change_path, 'a'):
                os.utime(change_path, None)
        except IOError as e:
            sys.stderr.write("{}\n".format(text_type(e)))
            return -1

    def run_install(self):
        home_dir = self.args.home or DEFAULT_HOME_DIR

        def create_dir(_path):
            path = os.path.join(home_dir, _path)
            try:
                if not os.path.exists(path):
                    os.makedirs(path)
                    sys.stdout.write("created '{}'\n".format(path))
            except OSError as e:
                if e.errno != 17:
                    raise

        for dirpath in ["", "sites-enabled", "sites-available"]:
            try:
                create_dir(dirpath)
            except OSError as e:
                if e.errno == 13:
                    sys.stderr.write('permission denied (do you need sudo)?\n')
                    return -1
                raise

        def write_file(_path, contents):
            path = os.path.join(home_dir, _path)
            if not self.args.force and os.path.exists(path):
                sys.stdout.write("not overwriting '{}' (use --force to overwrite)\n".format(path))
                return

            with open(path, 'wt') as f:
                f.write(contents)
            sys.stdout.write("wrote '{}'\n".format(path))

        for path, contents in [('moya.conf', DEFAULT_CONF),
                               ('logging.ini', DEFAULT_LOGGING),
                               ('bashtools', BASH_TOOLS)]:
            try:
                write_file(path, contents)
            except IOError as e:
                if e.errno == 13:
                    sys.stdout.write("permission denied writing '{}' (do you need sudo)?\n".format(path))
                    return -1
                else:
                    raise

        TOOLS_PATH = "~/.bashrc"
        bashtools_path = os.path.join(home_dir, 'bashtools')
        try:
            cmd = b'\n# Added by moya-srv install\nsource {}\n'.format(bashtools_path)
            bashrc_path = os.path.expanduser(TOOLS_PATH)
            if os.path.exists(bashrc_path):
                with open(bashrc_path, 'rb') as f:
                    bashrc = f.read()
            else:
                bashrc = b''
            if cmd not in bashrc:
                with open(bashrc_path, 'ab') as f:
                    f.write(cmd)
        except Exception as e:
            sys.stdout.write('unable to add moya service bash tools ({})\n'.format(e))
        else:
            sys.stdout.write('Added Moya service bash tools to {}\n'.format(TOOLS_PATH))
            sys.stdout.write("Tools will be available when you next log in (or run 'source {})\n".format(bashtools_path))

        sys.stdout.write('Moya service was installed in {}\n'.format(home_dir))


def main():
    moya_srv = MoyaSrv()
    sys.exit(moya_srv.run() or 0)
