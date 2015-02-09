from .. import iniparse
from fs.path import dirname, pathjoin


class Page(object):
    def __init__(self, doc_class, settings):
        self.doc_class = doc_class
        self.settings = settings

    def __repr__(self):
        return "Page(%r, %r)" % (self.doc_class, self.settings)

    def get(self, context, settings_name):
        return context.sub(self.settings.get(settings_name, ''))

    def get_path(self, context):
        return context.sub(self.settings.get('path', ''))


class Theme(object):
    def __init__(self, fs):
        self.fs = fs
        self.cfg = None
        self.theme_settings = None
        self.pages = []
        self.read()

    def get(self, section_name, key, default=None):
        section = self.cfg.get(section_name, None)
        if section is None:
            return default
        return section.get(key, default)

    def read(self):
        with self.fs.open('theme.ini', 'rb') as settings_file:
            cfg = iniparse.parse(settings_file)
        self.cfg = cfg

        self.theme_settings = cfg.get('theme', {})

        for section, settings in cfg.items():
            what, _, name = section.partition(':')
            if what == 'page':
                page = Page(name, settings)
                self.pages.append(page)

    def get_pages(self, doc):
        doc_class = doc.doc_class
        for page in self.pages:
            if page.doc_class == doc_class:
                yield page

    def get_relative_path(self, path):
        ini_path = dirname(self.fs.getsyspath('theme.ini'))
        path = pathjoin(ini_path, path)
        return path
