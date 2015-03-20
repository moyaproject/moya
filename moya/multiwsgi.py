from __future__ import unicode_literals
from __future__ import print_function

from moya.wsgi import WSGIApplication
from moya.sites import Sites
from moya.settings import SettingsContainer
from moya.compat import py2bytes, itervalues, text_type

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
</body>
</html>

"""


class Server(object):
    def __init__(self, name, domains, location, ini, logging, master_settings=None, master_logging=None):
        self.name = name
        self.domains = domains
        self.location = location
        self.ini = ini
        self.logging = logging
        self.master_logging = master_logging
        self.master_settings = master_settings

        self.application = None

    def __repr__(self):
        return "<server '{}'>".format(self.name)

    def build(self):
        log.debug('building %r', self)
        try:
            application = WSGIApplication(self.location,
                                          self.ini,
                                          logging=self.logging,
                                          master_settings=self.master_settings,
                                          master_logging=self.master_logging)
            application.build()
            self.application = application
        except:
            log.exception('error building %r', self)

    def rebuild(self):
        log.debug('re-building %r', self)
        try:
            application = WSGIApplication(self.location,
                                          self.ini,
                                          logging=self.logging,
                                          master_settings=self.master_settings,
                                          master_logging=self.master_logging)
            application.build()
        except Exception:
            log.debug('error re-building %r', self)
            return False
        else:
            self.application = application
        return True


class MultiWSGIApplication(object):

    def __init__(self):
        self.servers = OrderedDict()
        self.sites = Sites()
        self._lock = threading.Lock()

    def add_project(self, settings):
        name = settings.get('service', 'name')
        domains = settings.get_list('service', 'domains')
        location = os.path.join(self.home_dir, settings.get('service', 'location'))
        ini = settings.get_list('service', 'ini') or ['production.ini']
        logging_setting = settings.get('service', 'logging', None)
        if logging_setting is None:
            logging = 'logging.ini'
            master_logging = None
        else:
            logging = None
            master_logging = os.path.join(self.home_dir, logging_setting)

        server = Server(name, domains, location, ini, logging, master_settings=settings, master_logging=master_logging)
        self.servers[name] = server
        self.sites.add(domains, name=name)

    def build_all(self):
        for server in itervalues(self.servers):
            server.build()

    def not_found(self):
        response = Response(charset=py2bytes("utf8"), status=404)
        response.text = not_found_response

    def reload_required(server_name):
        return False

    def reload(self, server_name):
        log.debug("reloading '%s'", server_name)
        self.servers[server_name].rebuild()

    def __call__(self, environ, start_response):
        domain = environ['SERVER_NAME']
        site_match = self.sites.match(domain)
        if site_match is None:
            return self.not_found()
        server_name = site_match.data['name']
        if self.reload_required(server_name):
            log.debug("reload of '%s' required", server_name)
            with self._lock:
                if self.reload_required(server_name):
                    self.reload(server_name)
        server = self.servers[server_name]
        return server.application(environ, start_response)


class Service(MultiWSGIApplication):
    """WSGI applicaion to load projects from /etc/moya"""

    def error(self, msg, code=-1):
        sys.stderr.write(msg + '\n')
        sys.exit(code)

    def __init__(self, home_dir=None):
        super(Service, self).__init__()
        self.changes = {}

        self.home_dir = home_dir = os.environ.get('MOYA_SRV_HOME', None) or DEFAULT_HOME_DIR

        settings_path = os.path.join(home_dir, 'moya.conf')

        try:
            with io.open(settings_path, 'rt') as f:
                self.settings = SettingsContainer.read_from_file(f)
        except IOError:
            self.error('unable to read {}'.format(settings_path))
            return -1

        self.temp_dir = os.path.join(self.settings.get('service', 'temp_dir', tempfile.gettempdir()), 'moyasrv')
        try:
            os.makedirs(self.temp_dir)
        except OSError:
            pass

        for path in self._get_projects():
            settings = self._read_project(path)
            self.add_project(settings)

        for server_name in self.servers:
            path = os.path.join(self.temp_dir, "{}.changes".format(server_name))
            try:
                with open(path, 'a'):
                    os.utime(path, None)
            except IOError as e:
                sys.stderr.write("{}\n".format(text_type(e)))
                return -1
            self.changes[server_name] = os.path.getmtime(path)

        self.build_all()

    def reload_required(self, server_name):
        path = os.path.join(self.temp_dir, "{}.changes".format(server_name))
        mtime = os.path.getmtime(path)
        return self.changes[server_name] != mtime

    def reload(self, server_name):
        path = os.path.join(self.temp_dir, "{}.changes".format(server_name))
        self.changes[server_name] = os.path.getmtime(path)
        super(Service, self).reload(server_name)

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

    def _read_project(self, path):
        settings = SettingsContainer.read_os(path)
        return settings
