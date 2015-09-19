from . import settings
from .context.context import Context
from .context.color import Color
from .compat import text_type

from copy import copy
import json


import logging
log = logging.getLogger('moya.runtine')


class Theme(object):

    _cache = {}

    @classmethod
    def loader(cls, fs):
        """Automatically add theme to context"""
        def load(context):
            name = context.get('.sys.site.theme', 'default')

            if name in cls._cache:
                return copy(cls._cache[name])

            path = "{}.json".format(name)
            try:
                theme = cls.read(fs, path, context=context)
            except Exception as e:
                log.warning("unable to read theme file '%s' (%s)", path, text_type(e))

                if name != 'default':
                    return load('default')
                theme = None

            cls._cache[name] = theme
            return theme

        return load

    @classmethod
    def read(cls, fs, path, context=None):

        if context is None:
            context = Context()

        with fs.open(path, 'rb') as f:
            theme_data = json.load(f)

        # if 'colors' in theme_data:
        #     colors = {}
        #     for name, _color in theme_data['colors'].items():
        #         try:
        #             color = Color.parse(_color)
        #         except ValueError:
        #             log.error("failed to parse color '%s' from theme file '%s'", _color, path)
        #         else:
        #             colors[name] = color
        #     theme_data['colors'].update(colors)

        return theme_data
