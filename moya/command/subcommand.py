from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from ..compat import with_metaclass
from ..loggingconf import init_logging_fs

import logging
log = logging.getLogger('moya.startup')


class SubCommandMeta(type):
    registry = {}

    def __new__(cls, name, base, attrs):
        new_class = type.__new__(cls, name, base, attrs)
        if name != "SubCommand":
            cls.registry[name.lower()] = new_class
        return new_class


class SubCommandType(object):
    help = ''
    description = ''

    def __init__(self, command):
        self.command = command
        self.console = self.command.console

    def add_arguments(self, parser):
        pass

    def debug(self, text):
        return self.command.debug(text)

    def error(self, text):
        return self.command.error(text)

    def run(self):
        location = self.location
        init_logging_fs(self.location_fs, self.args.logging)
        log.debug('project found in "%s"', location)

    @property
    def location(self):
        return self.command.location

    @property
    def location_fs(self):
        return self.command.location_fs

    def get_settings(self):
        return self.command.get_settings()


class SubCommand(with_metaclass(SubCommandMeta, SubCommandType)):
    pass
