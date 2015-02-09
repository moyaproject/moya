from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from ..tools import get_moya_dir, is_moya_dir
from ..compat import with_metaclass
from ..loggingconf import init_logging

from fs.path import pathjoin

import logging
log = logging.getLogger('moya.startup')


class SubCommandMeta(type):
    registry = {}

    def __new__(cls, name, base, attrs):
        new_class = type.__new__(cls, name, base, attrs)
        if name != "SubCommand":
            cls.registry[name.lower()] = new_class
        return new_class


class NoProjectError(Exception):
    pass


class SubCommandType(object):
    help = ''
    description = ''

    def __init__(self, command):
        self.command = command
        self.console = self.command.console
        self._location = None

    def add_arguments(self, parser):
        pass

    def debug(self, text):
        return self.command.debug(text)

    def error(self, text):
        return self.command.error(text)

    def run(self):
        location = self.location
        init_logging(pathjoin(location, self.args.logging))
        log.debug('project found in "%s"', location)

    def init_logging(self, location):
        init_logging(logging)

    @property
    def location(self):
        if self._location is not None:
            return self._location
        location = self.args.location
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

    def get_settings(self):
        return self.command.get_settings()


class SubCommand(with_metaclass(SubCommandMeta, SubCommandType)):
    pass
