from __future__ import unicode_literals
from __future__ import print_function

import sys
import os.path
import argparse
import logging.config
import io
import importlib
from fs.path import pathjoin

from ..command.sub import __all__ as SUBCOMMANDS
from ..console import Console
from ..context import Context
from ..context.tools import set_dynamic
from ..tools import get_moya_dir, nearest_word
from ..errors import ElementNotFoundError
from ..compat import text_type
from ..command.subcommand import SubCommandMeta
from .. import db
from .. import settings
from .. import errors

from .. import __version__ as version

import logging
logging.raiseExceptions = False


class Command(object):
    description = ''

    def __init__(self):
        self.console = Console()
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
        if not settings:
            settings = self.moyarc.get('defaults', 'ini', 'settings.ini').strip()
        if not settings:
            return []
        ini_list = [s.strip() for s in settings.splitlines() if s.strip()]
        return ini_list

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

        if len(sys.argv) > 1 and sys.argv[1].count('#') == 1:
            return self.project_invoke(sys.argv[1])

        if len(sys.argv) > 1 and sys.argv[1] in SUBCOMMANDS:
            subcommand_module = 'moya.command.sub.{}'.format(sys.argv[1])
            importlib.import_module(subcommand_module)
        else:
            from .sub import *
        self.make_subcommands()

        parser = self.get_argparse()
        argv = [(v.decode(sys.getdefaultencoding()) if not isinstance(v, text_type) else v)
                for v in sys.argv[1:]]

        self.args = parser.parse_args(argv)

        if self.args.subcommand is None:
            parser.print_usage()
            return 1

        subcommand = self.subcommands[self.args.subcommand]
        subcommand.args = self.args
        subcommand.console = self.console
        subcommand.moyarc = self.moyarc

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

    def project_invoke(self, element_ref):

        parser = argparse.ArgumentParser(prog=self.__class__.__name__.lower() + " " + element_ref,
                                         description="Call command %s in moya project" % element_ref,
                                         version="1.0.0",
                                         add_help=False)

        parser.add_argument('-h', '--help', dest="help", action="store_true", default=False,
                            help="print help information")
        parser.add_argument('-d', '--debug', dest="debug", action="store_true", default=False,
                            help='enables debug output')
        parser.add_argument('-V', '--verbose', dest="verbose", action="store_true", default=False,
                            help='enables verbose output')
        parser.add_argument('--logging', dest="logging", default=None, help="path to logging configuration file", metavar="LOGGINGINI")
        parser.add_argument("-l", "--location", dest="location", default='./', metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to project settings file")
        parser.add_argument("-b", "--breakpoint", dest="breakpoint", action="store_true", default=False,
                            help="Start debugging at first element")

        args, remaining = parser.parse_known_args(sys.argv[2:])
        self.args = args
        show_help = args.help

        location = args.location
        try:
            location = get_moya_dir(location)
        except ValueError:
            self.error("Moya project directory not found")
            return -1

        if args.logging:
            logging.config.fileConfig(pathjoin(location, args.logging), disable_existing_loggers=False)
        else:
            log = logging.getLogger('moya.runtime')
            log.setLevel(logging.ERROR)

        from .. import pilot
        from ..wsgi import WSGIApplication

        try:
            application = WSGIApplication(location,
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

        if element_ref.endswith('#'):
            app_name = element_ref[:-1]
            try:
                app = archive.find_app(app_name)
            except errors.UnknownAppError:
                self.error("No app installed in the project with the name '%s'" % app_name)
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
        except ElementNotFoundError:
            self.error("Command '%s' not found" % element_ref)
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
                db.commit_sessions(context)

        # except LogicError, logic_error:
        #     if self.args.debug:
        #         logic_error.__moyaconsole__(self.console)
        #     else:
        #         self.console.error(unicode(logic_error))

        except KeyboardInterrupt:
            self.console.nl().div('user exit')

        except Exception as e:
            if hasattr(e, '__moyaconsole__'):
                e.__moyaconsole__(self.console)
            else:
                if self.args.debug:
                    self.console.div()
                self.console.exception(e, tb=self.args.debug)
                if self.args.debug:
                    self.console.div()

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
