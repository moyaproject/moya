from __future__ import unicode_literals
from __future__ import print_function

import sys
import os.path
import argparse
import logging.config
import locale
import io
import importlib

from ..command.sub import __all__ as all_subcommands
from ..console import Console
from ..context import Context
from ..context.tools import set_dynamic
from ..tools import get_moya_dir, is_moya_dir, nearest_word
from ..errors import ElementNotFoundError
from ..compat import text_type
from ..command.subcommand import SubCommandMeta
from ..multiwsgi import Service
from .. import db
from .. import settings
from .. import errors

from .. import __version__ as version

from fs.opener import open_fs

import logging
logging.raiseExceptions = False


class NoProjectError(Exception):
    pass


class Command(object):
    description = ''

    def __init__(self):
        self._console = None
        self.subcommands = {}

    def make_subcommands(self):
        self.subcommands = {name: cls(self)
                            for name, cls in SubCommandMeta.registry.items()}


class MoyaArgumentParser(argparse.ArgumentParser):
    """Some enhancements to argparse"""

    def _check_value(self, action, value):
        # converted value must be one of the choices (if specified)
        if action.choices is not None and value not in action.choices:

            nearest = nearest_word(value, action.choices)
            if nearest:
                msg = "invalid choice: '{}' (did you mean '{}')?\n".format(value, nearest)
            else:
                msg = "invalid choice: '{}'\n".format(value)
            self.print_usage()
            sys.stderr.write(msg)
            sys.exit(-1)


class Moya(Command):
    """Pilot for Moya web application server

Project commands may be called by giving the element reference as the first
parameter, e.g.

    moya auth#command.adduser -h

To list all available commands for a given application, omit the libname:

    moya auth#
"""

    def __init__(self):
        super(Moya, self).__init__()
        self._location = None
        self._location_fs = None
        self._master_settings = None

    @property
    def console(self):
        if self._console is None:
            color = self.moyarc.get_bool('console', 'color', True)
            self._console = Console(nocolors=not color)
        return self._console

    def get_default(self, name, default=None):
        return self.moyarc.get('defaults', name, default)

    def get_argparse(self):
        parser = MoyaArgumentParser(prog=self.__class__.__name__.lower(),
                                    description=getattr(self, '__doc__', ''),
                                    formatter_class=argparse.RawDescriptionHelpFormatter,
                                    epilog="Need help? http://moyaproject.com")

        parser.add_argument('-v', '--version', action='version', version=version)
        parser.add_argument('-d', '--debug', dest="debug", action="store_true", default=False,
                            help='enables debug output')
        parser.add_argument('--logging', dest="logging", default="logging.ini", help="set logging file")

        subparsers = parser.add_subparsers(title='available sub-commands',
                                           dest="subcommand",
                                           help="sub-command help")

        for name, subcommand in sorted(self.subcommands.items(), key=lambda item: item[0]):
            subparser = subparsers.add_parser(name,
                                              help=subcommand.help,
                                              description=getattr(subcommand, '__doc__', None))
            subcommand.add_arguments(subparser)

        return parser

    def get_settings(self):
        settings = self.args.settings

        moya_service = os.environ.get('MOYA_SERVICE_PROJECT', None)
        if moya_service is not None and self.master_settings is not None:
            settings = self.master_settings.get('service', 'ini', None)
        if not settings:
            settings = os.environ.get('MOYA_PROJECT_INI', None) or self.moyarc.get('defaults', 'ini', 'settings.ini').strip()
        if not settings:
            return []
        ini_list = [s.strip() for s in settings.splitlines() if s.strip()]
        return ini_list

    @property
    def master_settings(self):
        if self._master_settings is not None:
            return self._master_settings
        moya_service = os.environ.get('MOYA_SERVICE_PROJECT', None)
        if moya_service is None:
            self._master_settings = None
        else:
            self._master_settings = Service.get_project_settings(moya_service)
        return self._master_settings

    @property
    def location(self):
        if self._location is not None:
            return self._location
        location = None
        if self.master_settings:
            location = self.master_settings.get('service', 'location', None)
        location = self.args.location or location or os.environ.get('MOYA_PROJECT', None)
        if location is None:
            location = './'
        if location and '://' in location:
            return location
        try:
            location = get_moya_dir(location)
        except ValueError:
            raise NoProjectError("Moya project directory not found, run this command from a project directory or specify --location")
        if not is_moya_dir(location):
            raise NoProjectError("Location is not a moya project (no 'moya' file found)")
        self._location = location
        return location

    @property
    def location_fs(self):
        if self._location_fs is None:
            self._location_fs = open_fs(self.location)
        return self._location_fs

    def debug(self, text):
        """Write debug text, if enabled through command line switch"""
        if self.args.debug:
            self.console(text).nl()

    def error(self, text):
        """Write an error to the console"""
        self.console.error(text)

    def run(self):
        try:
            with io.open(os.path.expanduser("~/.moyarc"), 'rt') as f:
                self.moyarc = settings.SettingsContainer.read_from_file(f)
        except IOError:
            self.moyarc = settings.SettingsContainer()

        try:
            encoding = sys.stdin.encoding or locale.getdefaultlocale()[1]
        except:
            encoding = sys.getdefaultencoding()
        argv = [(v.decode(encoding, 'replace') if not isinstance(v, text_type) else v)
                for v in sys.argv]

        if len(argv) > 1 and argv[1].count('#') == 1:
            return self.project_invoke(argv[1])

        if len(argv) > 1 and argv[1] in all_subcommands:
            importlib.import_module('.' + argv[1], 'moya.command.sub')
        else:
            for name in all_subcommands:
                importlib.import_module('.' + name, 'moya.command.sub')

        self.make_subcommands()

        parser = self.get_argparse()

        self.args = parser.parse_args(argv[1:])

        if self.args.subcommand is None:
            parser.print_usage()
            return 1

        subcommand = self.subcommands[self.args.subcommand]
        subcommand.args = self.args
        subcommand.console = self.console
        subcommand.moyarc = self.moyarc
        subcommand.moya_command = self
        subcommand.master_settings = self.master_settings

        try:
            return subcommand.run()
        except KeyboardInterrupt as e:
            self.console.nl()
            if self.args.debug:
                self.console.exception(e, tb=True)
                self.console.div()
            return -1
        except Exception as e:
            if self.args.debug and hasattr(e, '__moyaconsole__'):
                e.__moyaconsole__(self.console)
            else:
                if self.args.debug:
                    self.console.div()
                self.console.exception(e, tb=self.args.debug)
                if self.args.debug:
                    self.console.div()

            return -1

    def project_invoke(self, element_ref, application=None, root_vars=None):

        parser = argparse.ArgumentParser(prog=self.__class__.__name__.lower() + " " + element_ref,
                                         description="Call command %s in moya project" % element_ref,
                                         add_help=False)

        parser.add_argument('-h', '--help', dest="help", action="store_true", default=False,
                            help="print help information")
        parser.add_argument('-d', '--debug', dest="debug", action="store_true", default=False,
                            help='enables debug output')
        parser.add_argument('-V', '--verbose', dest="verbose", action="store_true", default=False,
                            help='enables verbose output')
        parser.add_argument('--logging', dest="logging", default=None, help="path to logging configuration file", metavar="LOGGINGINI")
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to project settings file")
        parser.add_argument("-b", "--breakpoint", dest="breakpoint", action="store_true", default=False,
                            help="Start debugging at first element")

        args, remaining = parser.parse_known_args(sys.argv[2:])
        self.args = args
        show_help = args.help

        # location = args.location
        # try:
        #     location = get_moya_dir(location)
        # except ValueError:
        #     self.error("Moya project directory not found")
        #     return -1

        # if args.logging:
        #     logging.config.fileConfig(pathjoin(location, args.logging), disable_existing_loggers=False)
        # else:
        #     log = logging.getLogger('moya.runtime')
        #     log.setLevel(logging.ERROR)

        from .. import pilot
        from ..wsgi import WSGIApplication

        if application is None:
            try:
                application = WSGIApplication(self.location_fs,
                                              self.get_settings(),
                                              disable_autoreload=True)
            except Exception as e:
                self.console.exception(e)
                return -1
        archive = application.archive

        context = Context()
        application.populate_context(context)
        set_dynamic(context)
        # Ignore console settings for commands
        context['.console'] = self.console

        if root_vars is not None:
            context.root.update(root_vars)

        if element_ref.endswith('#'):
            app_name = element_ref[:-1]
            try:
                app = archive.find_app(app_name)
            except errors.UnknownAppError:
                self.error("No app called '%s' -- try 'moya apps'" % app_name)
                return -1
            commands = []
            for element in app.lib.get_elements_by_type('command'):
                commands.append(("moya " + element_ref + element.libname, element.synopsis(context)))
            if not commands:
                self.console.text("No commands available in %s" % app)
                return 0
            commands.sort()
            self.console.text("%s command(s) available in %s" % (len(commands), app), bold=True, fg="yellow")
            if commands:
                self.console.table(commands, header_row=("command", "synopsis"))
            return 0

        try:
            app, command_element = archive.get_app_element(element_ref)
        except errors.UnknownAppError:
            appname = element_ref.partition('#')[0]
            self.error("No app called '{}' -- try 'moya apps' to list available applications".format(appname))
            return -1
        except ElementNotFoundError:
            appname = element_ref.partition('#')[0]
            self.error("Command '{}' not found -- try 'moya {}#' to list available commands ".format(element_ref, appname))
            return -1
        synopsis = command_element.synopsis(context)

        parser.description = synopsis
        command_element.update_parser(parser, context)

        if show_help:
            parser.print_help()
            return 0

        args = parser.parse_args(remaining)

        ret = None
        try:
            context.root['server'] = application.server
            archive.populate_context(context)
            with pilot.manage(context):
                if self.args.breakpoint:
                    ret = archive.debug_call(element_ref,
                                             context,
                                             app,
                                             args=vars(args))
                else:
                    ret = archive.call(element_ref,
                                       context,
                                       app,
                                       args=vars(args))
                for thread in context.get('._threads', []):
                    thread.wait()
                context.safe_delete('._threads')
                db.commit_sessions(context)

        # except LogicError, logic_error:
        #     if self.args.debug:
        #         logic_error.__moyaconsole__(self.console)
        #     else:
        #         self.console.error(unicode(logic_error))

        except KeyboardInterrupt:
            self.console.nl().div('user exit')
            ret = -2

        except Exception as e:
            if hasattr(e, '__moyaconsole__'):
                e.__moyaconsole__(self.console)
            else:
                if self.args.debug:
                    self.console.div()
                self.console.exception(e, tb=self.args.debug)
                if self.args.debug:
                    self.console.div()
            ret = -2

        # except Exception, e:
        #     if self.args.debug:
        #         self.console.div()
        #     self.console.exception(e, tb=self.args.debug)
        #     if self.args.debug:
        #         self.console.div()

        return ret


def main():
    moya = Moya()
    return moya.run()


if __name__ == "__main__":
    sys.exit(main())
