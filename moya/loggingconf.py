from __future__ import print_function
from __future__ import unicode_literals

import io
from os.path import abspath, join, dirname, normpath
import logging
from logging import handlers

import fs.path
from fs.errors import FSError

from . import iniparse
from . import errors

MemoryHandler = handlers.MemoryHandler
log = logging.getLogger('moya.startup')


DEFAULT_LOGGING = """

[logger:root]
handlers=moyaconsole

[logger:moya]
level=DEBUG

[logger:moya.startup]

[logger:moya.signal]

[logger:sqlalchemy.engine]
handlers=moyaconsole
level=WARN
propagate=no

[handler:moyaconsole]
class=moya.logtools.MoyaConsoleHandler
formatter=simple
args=(sys.stdout,)

[handler:stdout]
class=StreamHandler
formatter=simple
args=(sys.stdout,)

[formatter:simple]
format=%(asctime)s:%(name)s:%(levelname)s: %(message)s
datefmt=[%d/%b/%Y %H:%M:%S]

"""


def _resolve(name):
    """Resolve a dotted name to a global object."""
    name = name.split('.')
    used = name.pop(0)
    found = __import__(used)
    for n in name:
        used = used + '.' + n
        try:
            found = getattr(found, n)
        except AttributeError:
            __import__(used)
            found = getattr(found, n)
    return found

_logging_level_names = {0: 'NOTSET',
                        10: 'DEBUG',
                        20: 'INFO',
                        30: 'WARNING',
                        40: 'ERROR',
                        50: 'CRITICAL',
                        'NOTSET': 0,
                        'DEBUG': 10,
                        'INFO': 20,
                        'WARN': 30,
                        'WARNING': 30,
                        'ERROR': 40,
                        'CRITICAL': 50}


def init_logging_fs(logging_fs, path, disable_existing_loggers=True, use_default=True):

    ini_path = path
    ini_stack = []
    parsed_default = False

    while 1:
        try:
            with logging_fs.open(path, 'rt') as ini_file:
                s = iniparse.parse(ini_file)
        except FSError:
            if use_default:
                s = iniparse.parse(DEFAULT_LOGGING)
                parsed_default = True
            else:
                raise errors.LoggingSettingsError('unable to read logging settings file "{}" from {}'.format(path, logging_fs.desc('/')))
        ini_stack.append(s)
        if "extends" in s['']:
            path = fs.path.join(fs.path.dirname(path), s['']['extends'])
        else:
            break
    _init_logging(ini_path, ini_stack, disable_existing_loggers)
    if parsed_default:
        log.warn('%s not found, using default logging', path)


def init_logging(path, disable_existing_loggers=True):
    """Sane logging.ini"""

    ini_path = path
    ini_stack = []
    visited = set()
    while 1:
        path = abspath(normpath(path))
        if path in visited:
            raise errors.LoggingSettingsError('recursive extends in logging ini')
        try:
            with io.open(path, 'rt') as ini_file:
                s = iniparse.parse(ini_file)
            visited.add(path)
        except IOError:
            raise errors.LoggingSettingsError('unable to read logging settings file "{}"'.format(path))
        ini_stack.append(s)
        if "extends" in s['']:
            path = join(dirname(path), s['']['extends'])
        else:
            break
    _init_logging(ini_path, ini_stack, disable_existing_loggers)


def _init_logging(path, ini_stack, disable_existing_loggers=True):
    ini_path = path
    ini_stack = ini_stack[::-1]
    ini = ini_stack[0]
    for extend_ini in ini_stack[1:]:
        for section_name, section in extend_ini.items():
            if section_name in ini:
                ini[section_name].update(section)
            else:
                ini[section_name] = section

    def get(section_name, key, default=Ellipsis):
        try:
            value = ini[section_name][key]
        except KeyError:
            if default is Ellipsis:
                raise errors.LoggingSettingsError('unable to initialize logging (required key [{}]/{} was not found in "{}")'.format(section_name, key, ini_path))
            return default
        return value

    def getint(section_name, key, default=Ellipsis):
        value = get(section_name, key, default)
        if not value.isdigit():
            raise errors.LoggingSettingsError('unable to initialize logging (setting [{}]/{} should be an integer in "{path}")'.format(section_name, key, ini_path))
        return int(value)

    def getbool(section_name, key, default=Ellipsis):
        value = get(section_name, key, default).strip().lower()
        if value in ('yes', 'true'):
            return True
        if value in ('no', 'false'):
            return False
        raise errors.LoggingSettingsError('unable to initialize logging (section [{}]/{} is not a valid boolean in "{path}"'.format(section_name, key, ini_path))

    logging._acquireLock()
    try:
        _handlers = {}
        _formatters = {}
        _loggers = {}
        for section_name in ini:
            if not section_name:
                continue
            what, _, name = section_name.partition(':')
            if what == 'handler':
                _handlers[name] = section_name
            elif what == 'formatter':
                _formatters[name] = section_name
            elif what == 'logger':
                _loggers[name] = section_name
            else:
                raise errors.LoggingSettingsError('unable to initialize logging (section [{}] is not valid in "{}")'.format(section_name, ini_path))

        formatters = {}
        for formatter_name, section_name in _formatters.items():
            opts = ini[section_name]
            if "format" in opts:
                fs = get(section_name, "format")
            else:
                fs = None
            if "datefmt" in opts:
                dfs = get(section_name, "datefmt")
            else:
                dfs = None
            c = logging.Formatter
            if "class" in opts:
                class_name = get(section_name, "class")
                if class_name:
                    c = _resolve(class_name)
            f = c(fs, dfs)
            formatters[formatter_name] = f

        handlers = {}
        handlers['null'] = logging.NullHandler()
        fixups = []
        for handler_name, section_name in _handlers.items():
            klass = get(section_name, 'class')
            opts = ini[section_name]
            if "formatter" in opts:
                fmt = get(section_name, "formatter")
            else:
                fmt = ""
            try:
                kass = eval(klass, vars(logging))
            except (AttributeError, NameError):
                kass = _resolve(klass)
            args = get(section_name, "args", "()")
            try:
                args = eval(args, vars(logging))
            except Exception as e:
                raise errors.LoggingSettingsError("error parsing logger '{}' args {} ({})".format(kass, args, e))
            try:
                h = kass(*args)
            except Exception as e:
                raise errors.LoggingSettingsError("error constructing logger '{}' with args {!r} ({})".format(kass, args, e))
            if "level" in opts:
                level = get(section_name, "level")
                h.setLevel(_logging_level_names[level])
            if len(fmt):
                h.setFormatter(formatters[fmt])
            if issubclass(kass, MemoryHandler):
                if "target" in opts:
                    target = get(section_name, "target")
                else:
                    target = ""
                if len(target):
                    fixups.append((h, target))
            handlers[handler_name] = h

        for h, t in fixups:
            h.setTarget(handlers[t])

        if 'root' not in _loggers:
            raise errors.LoggingSettingsError('unable to initialize logging (section [logger:root] is missing from "{}")'.format(ini_path))

        llist = list(_loggers.keys())
        llist.remove('root')

        root = logging.root
        log = root
        section_name = "logger:root"
        opts = ini[section_name]
        if "level" in opts:
            level = get(section_name, "level")
            log.setLevel(_logging_level_names[level])
        for h in root.handlers[:]:
            root.removeHandler(h)
        if 'handlers' in opts:
            hlist = [h.strip() for h in get(section_name, "handlers", 'null').split(',')]
            for hand in hlist:
                try:
                    log.addHandler(handlers[hand])
                except KeyError:
                    raise errors.LoggingSettingsError('''unable to initialize logging (handler '{}' not found in "{}")'''.format(hand, ini_path))

        existing = list(root.manager.loggerDict.keys())
        existing.sort()

        child_loggers = []
        for log in llist:
            section_name = "logger:{}".format(log)
            qn = get(section_name, "qualname", log)
            opts = ini[section_name]
            if "propagate" in opts:
                propagate = 1 if getbool(section_name, "propagate") else 0
            else:
                propagate = 1
            logger = logging.getLogger(qn)
            if qn in existing:
                i = existing.index(qn) + 1
                prefixed = qn + "."
                pflen = len(prefixed)
                num_existing = len(existing)
                while i < num_existing:
                    if existing[i][:pflen] == prefixed:
                        child_loggers.append(existing[i])
                    i += 1
                existing.remove(qn)
            if "level" in opts:
                level = get(section_name, "level", "NOTSET")
                if level not in _logging_level_names:
                    raise errors.LoggingSettingsError("unknown logging level '{}' in  [{}]".format(level, section_name))
                logger.setLevel(_logging_level_names[level])
            for h in logger.handlers[:]:
                logger.removeHandler(h)
            logger.propagate = propagate
            logger.disabled = 0

            if 'handlers' in opts:
                hlist = [h.strip() for h in get(section_name, "handlers", 'null').split(',')]
                for hand in hlist:
                    try:
                        logger.addHandler(handlers[hand])
                    except KeyError:
                        raise errors.LoggingSettingsError('''unable to initialize logging (handler '{}' not found in "{}")'''.format(hand, ini_path))

        for log in existing:
            logger = root.manager.loggerDict[log]
            if log in child_loggers:
                logger.level = logging.NOTSET
                logger.handlers = []
                logger.propagate = 1
            else:
                logger.disabled = disable_existing_loggers

    finally:
        logging._releaseLock()
