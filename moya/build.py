from __future__ import unicode_literals
from __future__ import print_function

from .archive import Archive
from .context import Context
from .parser import Parser
from . import tags
from . import errors
from .settings import SettingsContainer
from .filesystems import FSWrapper
from .compat import text_type, string_types, iteritems
from .tools import textual_list
from . import pilot

from fs.opener import open_fs
from fs.osfs import OSFS
from fs.multifs import MultiFS

import gc
import os
import sys
from time import time
from collections import namedtuple
from os.path import dirname, abspath

import logging
log = logging.getLogger('moya.runtime')
startup_log = logging.getLogger('moya.startup')


def read_config(fs, settings_path="settings.ini"):
    """Just read the config for a project"""
    if '://' in fs:
        fs = open_fs(fs)
    else:
        fs = OSFS(fs)
    cfg = SettingsContainer.read(fs, settings_path)
    return cfg


def build(fs,
          settings_path="settings.ini",
          rebuild=False,
          archive=None,
          strict=False,
          master_settings=None,
          test_build=False,
          develop=False):
    """Build a project"""
    if isinstance(fs, string_types):
        if '://' in fs:
            fs = open_fs(fs)
        else:
            fs = OSFS(fs)

    if isinstance(settings_path, string_types):
        settings_path = [settings_path]

    try:
        syspath = fs.getsyspath('/')
    except errors.NoSysPath:
        syspath = None

    cwd = os.getcwd()

    if syspath is not None:
        os.chdir(syspath)

    try:
        log.debug("reading settings from {}".format(textual_list(settings_path)))
        cfg = SettingsContainer.read(fs, settings_path, master=master_settings)

        if 'customize' in cfg:
            customize_location = cfg.get('customize', 'location')
            if customize_location:
                settings_path = cfg.get('customize', "settings", 'settings.ini')
                startup_log.info("customizing '%s'", customize_location)
                customize_fs = open_fs(cfg.get('customize', 'location'))

                cfg = SettingsContainer.read(customize_fs, settings_path, master=cfg)

                overlay_fs = MultiFS()
                overlay_fs.addfs('project', fs)
                overlay_fs.addfs('custom', customize_fs, write=True)
                fs = overlay_fs

                try:
                    syspath = fs.getsyspath('/', allow_none=True)
                except errors.NoSysPath:
                    pass
                else:
                    if syspath is not None:
                        os.chdir(syspath)

        if archive is None:
            archive = Archive(fs, strict=strict, test_build=test_build, develop=develop)
        context = Context()
        archive.cfg = cfg

        root = context.root
        root['libs'] = archive.libs
        root['apps'] = archive.apps
        root['fs'] = FSWrapper(fs)

        root['settings'] = SettingsContainer.from_dict(archive.cfg['settings'])
        startup_path = archive.cfg.get('project', 'startup')
        docs_location = archive.cfg.get('project', 'location')

        archive.init_settings()
        root['console'] = archive.console
        root['debug'] = archive.debug
        root['_rebuild'] = rebuild

        parser = Parser(archive, fs.opendir(docs_location), startup_path)
        doc = parser.parse()

        if doc is None:
            raise errors.StartupFailedError('unable to parse "{}"'.format(startup_path))

        archive.build(doc, fs=fs)

        return fs, archive, context, doc

    finally:
        os.chdir(cwd)
        gc.collect()


ServerBuildResult = namedtuple("ServerBuildResult",
                               ["archive",
                                "context",
                                "server"])


def render_failed_documents(archive, console, no_console=False):
    failed = 0
    for libname, lib in iteritems(archive.libs):
        for failed_doc in lib.failed_documents:
            failed += 1
            if not no_console:
                log.error("%s", failed_doc.msg)
                console.document_error(failed_doc.msg,
                                       failed_doc.path,
                                       failed_doc.code,
                                       failed_doc.line,
                                       failed_doc.col,
                                       diagnosis=failed_doc.diagnosis)
    for failed_doc in archive.failed_documents:
        failed += 1
        if not no_console:
            log.error("%s", failed_doc.msg)
            console.document_error(failed_doc.msg,
                                   failed_doc.path,
                                   failed_doc.code,
                                   failed_doc.line,
                                   failed_doc.col,
                                   diagnosis=failed_doc.diagnosis)

    return failed


def build_lib(location, archive=None, dependancies=None, ignore_errors=False, tests=False):
    """Build a project with a single lib (for testing)"""
    if archive is None:
        archive = Archive()

    if location.startswith('py:'):
        py = location.split(':', 1)[1]
        __import__(py)
        module = sys.modules[py]
        location = dirname(abspath(module.__file__))

    with open_fs(location) as import_fs:
        lib = archive.load_library(import_fs)

    if tests:
        dependancies = lib._cfg.get_list('tests', 'import') or []

    if dependancies:
        for require_lib in dependancies:
            if require_lib.startswith('py:'):
                py = require_lib.split(':', 1)[1]
                __import__(py)
                module = sys.modules[py]
                location = dirname(abspath(module.__file__))
            else:
                location = require_lib
            with open_fs(location) as import_fs:
                _lib = archive.load_library(import_fs)

    archive.finalize(ignore_errors=ignore_errors)

    return archive, lib


def get_lib_info(location, archive=None):
    if archive is None:
        archive = Archive()

    if location.startswith('py:'):
        py = location.split(':', 1)[1]
        __import__(py)
        module = sys.modules[py]
        location = dirname(abspath(module.__file__))

    with open_fs(location) as import_fs:
        cfg = SettingsContainer.read(import_fs, 'lib.ini')

    return cfg


def build_server(fs,
                 settings_path,
                 server_element="main",
                 no_console=False,
                 rebuild=False,
                 validate_db=False,
                 breakpoint=False,
                 strict=False,
                 master_settings=None,
                 test_build=False,
                 develop=False):
    """Build a server"""
    start = time()
    archive = Archive()
    console = archive.console
    project_fs = None
    try:
        (project_fs,
         archive,
         context,
         doc) = build(fs,
                      settings_path,
                      rebuild=rebuild,
                      strict=strict,
                      master_settings=master_settings,
                      test_build=test_build,
                      develop=develop)
        console = archive.console
    except errors.ParseError as e:
        if not no_console:
            line, col = e.position
            console.document_error(text_type(e),
                                   e.path,
                                   e.code,
                                   line,
                                   col)
        return None
    except errors.ElementError as element_error:
        if not no_console:
            line = element_error.source_line
            col = 0
            console.document_error(text_type(element_error),
                                   element_error.element._location,
                                   element_error.element._code,
                                   line,
                                   col)
        raise errors.StartupFailedError('Failed to build project')

    if project_fs is None:
        if isinstance(fs, string_types):
            if '://' in fs:
                fs = open_fs(fs)
            else:
                fs = OSFS(fs)
    archive.project_fs = project_fs

    try:
        app, server = doc.get_element(server_element)
    except errors.ElementNotFoundError:
        raise errors.StartupFailedError("no <server> element called '{}' found in the project (check setting [project]/startup)".format(server_element))
    error_msg = None
    docs_location = archive.cfg.get('project', 'location')
    try:
        with pilot.manage_request(None, context):
            server.startup(archive, context, project_fs.opendir(docs_location), breakpoint=breakpoint)
    except errors.StartupFailedError as error:
        error_msg = text_type(error)
        #raise
    except errors.ElementError as e:
        raise
    except Exception as e:
        failed = render_failed_documents(archive, console, no_console=no_console)
        if failed:
            raise errors.StartupFailedError("{} document(s) failed to build".format(failed))

        if hasattr(e, '__moyaconsole__'):
            e.__moyaconsole__(console)
        error_msg = text_type(e)
        raise errors.StartupFailedError(error_msg or 'Failed to build project')

    failed = render_failed_documents(archive, console, no_console=no_console)
    if failed:
        raise errors.StartupFailedError(error_msg or 'Failed to build project')

    archive.init_media()
    archive.init_data()

    if validate_db:
        from . import db
        if db.validate_all(archive, console) == 0:
            startup_log.debug('models validated successfully')
        else:
            msg = "Models failed to validate, see 'moya db validate' for more information"
            raise errors.StartupFailedError(msg)

    startup_log.info("%s built %.1fms", server, (time() - start) * 1000.0)
    return ServerBuildResult(archive=archive,
                             context=context,
                             server=server)


if __name__ == "__main__":
    build_server("./example")
