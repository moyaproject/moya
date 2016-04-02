from __future__ import unicode_literals
from __future__ import print_function

from moya.wsgi import WSGIApplication
from moya.sites import Sites
from moya.settings import SettingsContainer
from moya.compat import py2bytes, itervalues, text_type
from moya.loggingconf import init_logging

from webob import Response

import sys
import os
import io
import glob
import tempfile
import threading
from collections import OrderedDict


import logging
log = logging.getLogger('moya.srv')


DEFAULT_HOME_DIR = "/etc/moya"

not_found_response = """<!DOCTYPE html>
<html>
<head>
    <title>404 Not Found</title>
    <style type="text/css">
        body {{font-family: arial,sans-serif;}}
    </style>
</head>
<body>
<h1>404 Not Found</h1>
<small>moya-srv does not know about this domain</small>
</body>
</html>
"""


class Server(object):
    def __init__(self, settings_path):
        self.settings_path = settings_path
        self.load()
        self.application = None

    def load(self):
        settings = SettingsContainer.read_os(self.settings_path)

        self.name = settings.get('service', 'name')
        self.domains = settings.get_list('service', 'domains')
        self.location = settings.get('service', 'location')
        self.ini = settings.get_list('service', 'ini') or ['production.ini']

        self.master_settings = settings

    def __repr__(self):
        return "<project '{}'>".format(self.name)

    def build(self):
        log.debug('building %r', self)
        try:
            application = WSGIApplication(self.location,
                                          self.ini,
                                          disable_autoreload=True,
                                          logging=None,
                                          master_settings=self.master_settings)
            self.application = application
        except:
            log.exception('error building %r', self)
            raise


class MultiWSGIApplication(object):

    def __init__(self):
        self.servers = OrderedDict()
        self.sites = Sites()
        self._lock = threading.Lock()

    def add_project(self, settings_path, logging_path=None):
        server = Server(settings_path)
        self.servers[server.name] = server
        self.sites.add(server.domains, name=server.name)
        log.debug('registered %r', server)

    def build_all(self):
        for server in itervalues(self.servers):
            server.build()

    def not_found(self):
        response = Response(charset=py2bytes("utf8"), status=404)
        response.text = not_found_response
        return response.app_iter

    def reload_required(server_name):
        return False

    def reload(self, server_name):
        """
        Reload the server

        This actually creates a new server object, so that if the load fails it will continue to
        process requests with the old server instance.
        """

        log.debug("reloading '%s'", server_name)

        server = self.servers[server_name]
        try:
            new_server = Server(server.settings_path)
            new_server.build()
        except:
            log.exception("reload of '%s' failed", server_name)
        else:
            self.servers[server_name] = new_server
            self.sites.clear()
            for server in itervalues(self.servers):
                self.sites.add(server.domains, name=server.name)

    def __call__(self, environ, start_response):
        try:
            domain = environ['SERVER_NAME']
            with self._lock:
                site_match = self.sites.match(domain)
                if site_match is None:
                    return self.not_found()
                server_name = site_match['name']
                if self.reload_required(server_name):
                    self.reload(server_name)
                server = self.servers[server_name]
            return server.application(environ, start_response)
        except:
            log.exception('error in multiwsgi MultiWSGIApplication.__call__')
            raise


class Service(MultiWSGIApplication):
    """WSGI application to load projects from /etc/moya"""

    def error(self, msg, code=-1):
        sys.stderr.write(msg + '\n')
        sys.exit(code)

    def __init__(self, home_dir=None):
        super(Service, self).__init__()
        self.changes = {}

        self.home_dir = home_dir = os.environ.get('MOYA_SERVICE_HOME', None) or DEFAULT_HOME_DIR
        settings_path = os.path.join(home_dir, 'moya.conf')

        try:
            with io.open(settings_path, 'rt') as f:
                self.settings = SettingsContainer.read_from_file(f)
        except IOError:
            self.error('unable to read {}'.format(settings_path))
            return -1

        logging_setting = self.settings.get('projects', 'logging', 'logging.ini')
        logging_path = os.path.join(self.home_dir, logging_setting)

        try:
            init_logging(logging_path)
        except Exception as e:
            log.error("unable to initialize logging from '%s'", logging_path)
            sys.stderr.write("unable to initialize logging from '{}' ({})\n".format(logging_path, e))
            return -1

        log.debug('read conf from %s', settings_path)
        log.debug('read logging from %s', logging_path)

        temp_dir_root = self.settings.get('service', 'temp_dir', tempfile.gettempdir())
        self.temp_dir = os.path.join(temp_dir_root, 'moyasrv')
        try:
            os.makedirs(self.temp_dir)
        except OSError:
            pass

        for path in self._get_projects(self.settings, self.home_dir):
            log.debug('reading project settings %s', path)
            try:
                self.add_project(path)
            except:
                log.exception("error adding project from '%s'", path)

        for server_name in self.servers:
            path = os.path.join(self.temp_dir, "{}.changes".format(server_name))
            try:
                if not os.path.exists(path):
                    with open(path, 'wb'):
                        pass
            except IOError as e:
                sys.stderr.write("{}\n".format(text_type(e)))
                return -1
            self.changes[server_name] = os.path.getmtime(path)

        self.build_all()

    @classmethod
    def get_project_settings(cls, project_name):
        """Get the settings for a single project"""
        home_dir = os.environ.get('MOYA_SERVICE_HOME', None) or DEFAULT_HOME_DIR
        settings_path = os.path.join(home_dir, 'moya.conf')

        try:
            with io.open(settings_path, 'rt') as f:
                service_settings = SettingsContainer.read_from_file(f)
        except IOError:
            log.error("unable to read moya service settings from '{}'", settings_path)
            return -1

        for path in cls._get_projects(service_settings, home_dir):
            try:
                settings = SettingsContainer.read_os(path)
            except Exception as e:
                log.error("error reading '%s' (%s)", path, e)
            if settings.get('service', 'name', None) == project_name:
                return settings
        return None

    def reload_required(self, server_name):
        """Detect if a reload is required"""
        path = os.path.join(self.temp_dir, "{}.changes".format(server_name))
        mtime = os.path.getmtime(path)
        return self.changes[server_name] != mtime

    def reload(self, server_name):
        path = os.path.join(self.temp_dir, "{}.changes".format(server_name))
        self.changes[server_name] = os.path.getmtime(path)
        super(Service, self).reload(server_name)

    @classmethod
    def _get_projects(self, settings, home_dir):
        project_paths = settings.get_list('projects', 'read')
        paths = []
        cwd = os.getcwd()
        try:
            os.chdir(home_dir)
            for path in project_paths:
                glob_paths = glob.glob(path)
                paths.extend([os.path.abspath(p) for p in glob_paths])
        finally:
            os.chdir(cwd)
        return paths
