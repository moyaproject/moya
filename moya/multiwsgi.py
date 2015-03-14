from __future__ import unicode_literals
from __future__ import print_function

from moya.wsgi import WSGIApplication
from moya.sites import Sites
from moya.settings import SettingsContainer
from moya.compat import py2bytes, itervalues

from webob import Response

import sys
import os
import io
import glob
from collections import OrderedDict


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

    def build(self):
        application = WSGIApplication(self.location,
                                      self.ini,
                                      logging=self.logging,
                                      master_settings=self.master_settings,
                                      master_logging=self.master_logging)
        application.build()
        self.application = application


class MultiWSGIApplication(object):

    def __init__(self):
        self.servers = OrderedDict()
        self.sites = Sites()

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

    def __call__(self, environ, start_response):
        domain = environ['SERVER_NAME']
        site_match = self.sites.match(domain)
        if site_match is None:
            return self.not_found()
        server_name = site_match.data['name']
        server_application = self.servers[server_name].application
        return server_application(environ, start_response)


class Service(MultiWSGIApplication):

    def error(self, msg, code=-1):
        sys.stderr.write(msg + '\n')
        sys.exit(code)

    def __init__(self, home_dir=None):
        super(Service, self).__init__()
        self.home_dir = home_dir = os.environ.get('MOYA_SRV_HOME', None) or DEFAULT_HOME_DIR

        settings_path = os.path.join(home_dir, 'moya.conf')
        try:
            with io.open(settings_path, 'rt') as f:
                self.settings = SettingsContainer.read_from_file(f)
        except IOError:
            self.error('unable to read {}'.format(settings_path))
            return -1

        for path in self._get_projects():
            settings = self._read_project(path)
            self.add_project(settings)

        self.build_all()

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
