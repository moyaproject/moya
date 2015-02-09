from __future__ import print_function
from __future__ import unicode_literals

import io

from . import iniparse
from . import errors
import logging
from logging import handlers
MemoryHandler = handlers.MemoryHandler

from os.path import abspath, join, dirname


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


def init_logging(path, disable_existing_loggers=False):
    """Sane logging.ini"""

    ini_path = path
    ini_stack = []
    while 1:
        path = abspath(path)
        try:
            with io.open(path, 'rt') as ini_file:
                s = iniparse.parse(ini_file)
        except IOError:
            raise errors.LoggingSettingsError('unable to read logging settings file "{}"'.format(path))
        ini_stack.append(s)
        if "extends" in s['']:
            path = join(dirname(path), s['']['extends'])
        else:
            break

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
            args = get(section_name, "args")
            args = eval(args, vars(logging))
            h = kass(*args)
            if "level" in opts:
                level = get(section_name, "level")
                h.setLevel(logging._levelNames[level])
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

        llist = _loggers.keys()
        llist.remove('root')

        root = logging.root
        log = root
        section_name = "logger:root"
        opts = ini[section_name]
        if "level" in opts:
            level = get(section_name, "level")
            print(level)
            log.setLevel(logging._levelNames[level])
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
                if level not in logging._levelNames:
                    raise errors.LoggingSettingsError("unknown logging level '{}' in  [{}]".format(level, section_name))
                logger.setLevel(logging._levelNames[level])
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
