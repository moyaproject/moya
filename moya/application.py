from __future__ import unicode_literals

from .compat import iteritems

import logging
import weakref

from fs.path import abspath, forcedir


class Application(object):
    def __init__(self, archive, name, lib_id):
        self._archive = weakref.ref(archive)
        self.name = name
        self.lib = archive.get_library(lib_id)
        self.settings = self.lib.settings.copy()
        self.system_settings = self.lib.system_settings.copy()
        self.filters = self._bind_filters(self.lib.filters)
        self.media = {}
        self.urls = None
        self.mounts = []

        self._templates_directory = None

    @property
    def enum(self):
        return self.lib.enum

    @property
    def archive(self):
        return self._archive()

    @property
    def templates_directory(self):
        if self._templates_directory is None:
            self._templates_directory = forcedir(abspath(self.system_settings['templates_directory']))
        return self._templates_directory

    @property
    def data_directory(self):
        return abspath(self.system_settings['data_directory'])

    @property
    def default_template(self):
        return self.system_settings.get('default_template', "/base.html")

    @property
    def log(self):
        log = logging.getLogger('moya.app.{}'.format(self.name))
        return log

    def __moya_application__(self):
        return self

    def resolve_template(self, template, check=False):
        if template is None:
            return None
        path = self.archive.resolve_template_path(template, self.name)
        if check:
            self.archive.get_template_engine().check(template)
        return path

    def resolve_templates(self, templates, check=False):
        if not templates:
            return None
        engine = self.archive.get_template_engine()
        template_exists = engine.exists
        path = None
        for template in templates:
            path = self.resolve_template(template)
            if template_exists(path):
                break
        else:
            if check:
                from .template.errors import MissingTemplateError
                raise MissingTemplateError(path)
        return path

    def get_element(self, element_ref):
        archive = self.archive
        app_id, lib_id, name = archive.parse_element_ref(element_ref)
        app_lib_id = app_id or lib_id
        if app_lib_id:
            app = archive.find_app(app_lib_id)
        else:
            app = self
        return archive.get_element('#' + name, app=app)

    def qualify_ref(self, ref):
        """qualify an element reference with this app name"""
        if '#' in ref:
            return "{}#{}".format(self.name, ref.split('#', 1)[-1])
        return ref

    def get_media_directory(self, media):
        return self.media.get(media, '')

    def _bind_filters(self, filters):
        bound_filters = {}
        for name, _filter in iteritems(filters):
            if hasattr(_filter, '__moyabind__'):
                _filter = _filter.__moyabind__(self)
            bound_filters[name] = _filter
        return bound_filters

    def throw(self, exc_type, msg, diagnosis=None, **info):
        """Throw a Moya exception"""
        from .logic import MoyaException
        raise MoyaException(exc_type, msg, diagnosis=diagnosis, info=info)

    def __repr__(self):
        return '<application %s:%s>' % (self.lib.long_name, self.name)
