from __future__ import unicode_literals
from __future__ import print_function

import weakref

from ..compat import string_types
from .errors import MissingTemplateError, BadTemplateError
from .moyatemplates import Template
from ..cache.dictcache import DictCache

from fs.info import Info as FSInfo
from fs.path import abspath, normpath
from fs.opener import open_fs
from fs.errors import ResourceNotFound, NoSysPath


# Update for backwards incompatible changes, so we don't get old cached templates
TEMPLATE_VERSION = 9


class Environment(object):
    name = "moya"

    def __init__(self, template_fs, archive=None, cache=None):
        if isinstance(template_fs, string_types):
            template_fs = open_fs(template_fs)
        self.template_fs = template_fs
        if archive is not None:
            self._archive = weakref.ref(archive)
            self.cache = cache or archive.get_cache('templates')
        else:
            self._archive = lambda: None
            if cache is None:
                cache = DictCache("templates", "")
            self.cache = cache
        self.templates = {}
        self._caches = {}

    @classmethod
    def make_default(self):
        return Environment(open_fs('mem://'))

    @property
    def archive(self):
        return self._archive()

    def check_template(self, template_path):
        """Check if a template exists"""
        template_path = abspath(normpath(template_path))
        if template_path in self.templates:
            return
        if not self.template_fs.exists(template_path):
            raise MissingTemplateError(template_path)

    def get_template(self, template_path, parse=True):
        template_path = abspath(normpath(template_path))
        template = self.templates.get(template_path, None)
        if template is not None:
            return template
        if self.cache.enabled:
            try:
                info = self.template_fs.getdetails(template_path)
            except ResourceNotFound:
                raise MissingTemplateError(template_path)
            cache_name = "%s$%s@%s" % (TEMPLATE_VERSION, template_path, info.modified)
            cached_template = self.cache.get(cache_name, None)
            if cached_template is not None:
                template = Template.load(cached_template)
                self.templates[template_path] = template
                return template

        try:
            source = self.template_fs.gettext(template_path)
        except ResourceNotFound:
            raise MissingTemplateError(template_path)
        except Exception:
            raise BadTemplateError(template_path)

        try:
            display_path = self.template_fs.getsyspath(template_path)
        except NoSysPath:
            display_path = template_path
        if self.archive is None:
            lib = None
        else:
            lib = self.archive.get_template_lib(template_path)

        template = Template(source, display_path, raw_path=template_path, lib=lib)
        template.parse(self)

        if self.cache.enabled:
            self.cache.set(cache_name, template.dump(self))

        self.templates[template_path] = template
        return template

    def compile_template(self, source, path):
        template = Template(source, path)
        return template

    def get_cache(self, cache_name):
        if self.archive is not None:
            return self.archive.get_cache(cache_name)
        if cache_name not in self._caches:
            self._caches[cache_name] = DictCache(cache_name, "")
        return self._caches[cache_name]
