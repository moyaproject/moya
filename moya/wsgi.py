from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from .build import build_server
from . import errors
from . import pilot
from . import db
from .context import Context
from . import tags
from .tags import cookie
from .tools import timer
from .logic import debug_lock, is_debugging
from .logic import _notify
from .request import MoyaRequest, ReplaceRequest
from .response import MoyaResponse
from . import http
from .compat import text_type, itervalues, py2bytes
from . import namespaces
from .loggingconf import init_logging

from webob import Response

from fs.path import splitext, pathjoin
from fs.opener import fsopendir
from fs.watch import CREATED, MODIFIED, REMOVED, MOVED_DST, MOVED_SRC

from time import time, clock
from threading import RLock
import weakref
from collections import defaultdict
from textwrap import dedent

import logging
log = logging.getLogger("moya")
request_log = logging.getLogger("moya.request")
startup_log = logging.getLogger("moya.startup")
preflight_log = logging.getLogger("moya.preflight")


#import moya.debugprint

class ReloadChangeWatcher(object):

    def __init__(self, watch_location, app):
        self._app = weakref.ref(app)
        self.watch_types = app.archive.cfg.get_list("autoreload", "extensions", ".xml\n.ini\n.py")
        self.watching_fs = fsopendir(watch_location)
        self.watching_fs.add_watcher(self.on_change, '/', (CREATED, MODIFIED, REMOVED, MOVED_DST, MOVED_SRC))
        startup_log.debug('watching "{}" for changes'.format(watch_location))

    @property
    def app(self):
        return self._app()

    def on_change(self, event):
        if self.app is None or not hasattr(self.app, 'archive'):
            return
        ext = splitext(event.path)[1].lower()
        if ext not in self.watch_types:
            return
        if isinstance(event, MODIFIED) and not event.closed:
            return

        if not self.app.rebuild_required:
            log.info("detected modification to project, rebuild will occur on next request")
        self.app.rebuild_required = True


class WSGIApplication(object):

    def __init__(self,
                 filesystem_url,
                 settings_path,
                 server="main",
                 logging=None,
                 disable_autoreload=False,
                 breakpoint=False,
                 breakpoint_startup=False,
                 validate_db=False):
        self.filesystem_url = filesystem_url
        self.settings_path = settings_path
        self.server_ref = server
        self.logging = logging
        self.breakpoint = breakpoint
        self.validate_db = validate_db
        self.watching_fs = None
        self.rebuild_required = False
        self._new_build_lock = RLock()
        self.archive = None
        self._self = weakref.ref(self, self.on_close)

        if logging is not None:
            init_logging(pathjoin(self.filesystem_url, logging))
        try:
            self.build(breakpoint=breakpoint_startup)
        except Exception as e:
            startup_log.critical(text_type(e))
            raise

        if self.archive.auto_reload and not disable_autoreload:
            watch_location = self.archive.cfg.get('autoreload', 'location', '')
            watch_location = pathjoin(self.filesystem_url, watch_location)
            self.watcher = ReloadChangeWatcher(watch_location, self)

    @classmethod
    def on_close(cls, application_weakref):
        # Called prior to Python finalizing the WSGIApplication, but before __del__
        # Note, application_weakref will always return None. There is no way to use the original object at this point
        pass

    # def __del__(self):
    #     pass

    def __repr__(self):
        return """<wsgiapplication {} {}>""".format(self.settings_path, self.server_ref)

    def build(self, breakpoint=False):
        with timer('startup', output=startup_log.debug):
            build_result = build_server(self.filesystem_url,
                                        self.settings_path,
                                        server_element=self.server_ref,
                                        validate_db=self.validate_db,
                                        breakpoint=breakpoint)
        if build_result is None:
            msg = "Failed to build project"
            raise errors.StartupFailedError(msg)

        self.archive = build_result.archive
        self.archive.finalize()
        self.server = build_result.server

        context = Context({"console": self.archive.console,
                           "settings": self.archive.settings,
                           "debug": self.archive.debug,
                           "develop": self.archive.develop,
                           "pilot": pilot})

        self.populate_context(context)
        self.archive.populate_context(context)
        self.archive.fire(context, "sys.startup")
        db.commit_sessions(context)

    def populate_context(self, context):
        # Called by moya <command>
        context.root.update(_dbsessions=db.get_session_map(self.archive),
                            console=self.archive.console,
                            fs=self.archive.get_context_filesystems())

    def do_rebuild(self):
        self.archive.console.div("Re-building project due to changes", bold=True, fg="blue")

        error_text = None
        try:
            new_build = build_server(self.filesystem_url,
                                     self.settings_path,
                                     server_element=self.server_ref,
                                     validate_db=True)
        except Exception as e:
            error_text = text_type(e)
            log.warning(e)
            new_build = None

        if new_build is None:
            self.rebuild_required = False
            _notify("Rebuild Failed", error_text or "Unable to build project, see console")
            return

        with self._new_build_lock:
            self.archive = new_build.archive
            self.server = new_build.server
            self.archive.finalize()
        import gc
        gc.collect()
        self.rebuild_required = False
        self.archive.console.div("Modified project built successfully", bold=True, fg="green")

    def preflight(self, report=True):
        app_preflight = []

        if self.archive.preflight:
            for app in itervalues(self.archive.apps):
                preflight = []
                for element in app.lib.get_elements_by_type((namespaces.preflight, "check")):
                    preflight_callable = self.archive.get_callable_from_element(element, app=app)

                    context = Context({"preflight": preflight})
                    self.archive.populate_context(context)
                    self.populate_context(context)
                    try:
                        preflight_callable(context, app=app)
                    except Exception as e:
                        preflight.append((element, "error", text_type(e)))
                app_preflight.append((app, preflight))
            if report:
                all_ok = True
                for app, checks in app_preflight:
                    if not checks:
                        continue
                    totals = defaultdict(int)
                    for element, status, text in checks:
                        lines = dedent(text).splitlines()
                        totals[status] += 1
                        for line in lines:
                            if line:
                                if status == "warning":
                                    preflight_log.warning('%s', line)
                                elif status == "fail":
                                    preflight_log.error('%s', line)
                                elif status == "error":
                                    preflight_log.critical('%s', line)

                    results = []
                    for status in ("warning", "fail", "error"):
                        if totals[status]:
                            results.append("{} {}(s)".format(totals[status], status))
                            all_ok = False
                    if results:
                        preflight_log.info("%s in %s", ", ".join(results), app)

                if all_ok:
                    preflight_log.info("all passed")
                else:
                    preflight_log.warning("preflight detected potential problems -- run 'moya preflight' for more information")

        return app_preflight

    def get_response(self, request, context):
        """Get a response object"""
        fire = self.archive.fire

        fire(context, "request.start", app=None, sender=None, data={'request': request})

        with pilot.manage_request(request, context):

            root = context.root
            root.update(settings=self.archive.settings,
                        debug=self.archive.debug,
                        request=request,
                        cookiejar=cookie.CookieJar())
            self.populate_context(context)

            fire(context, "request.pre-dispatch", data={'request': request})
            while 1:
                try:
                    result = self.server.dispatch(self.archive, context, request, breakpoint=self.breakpoint)
                except Exception:
                    log.exception("error in dispatch")
                    raise

                if isinstance(result, ReplaceRequest):
                    context.root['request'] = request = result.request
                    continue
                break

            fire(context, "request.post-dispatch", data={'request': request, 'result': result})

            response = None
            if result is not None:
                if isinstance(result, text_type):
                    response = MoyaResponse(charset=py2bytes('utf8'),
                                            text=text_type(result))
                elif isinstance(result, Response):
                    response = result
            else:
                response = context.root.get("response", None)

            if response is None:
                response = MoyaResponse(status=http.StatusCode.not_found,
                                        text=py2bytes("404 - Not Found"))

            if 'headers' in root:
                for k, v in root['headers'].items():
                    response.headers[k.encode('utf-8')] = v.encode('utf-8')

        fire(context, "request.response", data={'request': request, 'response': response})
        return response

    def __call__(self,
                 environ,
                 start_response):
        """Build the request"""

        if not is_debugging() and self.rebuild_required:
            with debug_lock:
                self.do_rebuild()

        start = time()
        start_clock = clock()
        context = Context()
        request = MoyaRequest(environ)
        response = self.get_response(request, context)

        start_response(response.status,
                       response.headerlist)

        taken = time() - start
        clock_taken = clock() - start_clock
        taken_ms = "{:.1f}ms {:.1f}ms".format(taken * 1000, clock_taken * 1000)
        request_log.info('"%s %s %s" %i %s %s',
                         request.method,
                         request.path_qs,
                         request.http_version,
                         response.status_int,
                         response.content_length,
                         taken_ms)
        yield response.body
        self.archive.fire(context,
                          "request.end",
                          data={'response': response})

Application = WSGIApplication
