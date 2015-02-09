from __future__ import unicode_literals

import weakref

from ..compat import with_metaclass


class TemplateEngineMeta(type):
    template_engines = {}

    def __new__(cls, name, base, attrs):
        new_class = type.__new__(cls, name, base, attrs)
        if name != "TemplateEngine":
            name = getattr(new_class, 'name', name.lower().strip('_'))
            cls.template_engines[name] = new_class
        return new_class


class TemplateEngineType(object):

    def __init__(self, archive, fs, settings):
        super(TemplateEngineType, self).__init__()
        self._archive = weakref.ref(archive) if archive else (lambda: None)
        self.fs = fs
        self.settings = settings

    @property
    def weakref(self):
        return self._archive()

    @classmethod
    def create(cls, system, archive, fs, settings):
        engine = TemplateEngineMeta.template_engines[system](archive, fs, settings)
        return engine


class TemplateEngine(with_metaclass(TemplateEngineMeta, TemplateEngineType)):
    pass
