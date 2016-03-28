from .context.context import Context
from .compat import text_type
from . import pilot

import json
import hashlib
import logging
log = logging.getLogger('moya.runtine')


DEFAULT = """
{
    "_moya":
    {
        "note": "internal default"
    },
    "colors":
    {
        "text":
        {
            "fg": "black",
            "bg": "white"
        },
        "highlight":
        {
            "fg": "black",
            "bg": "wheat"
        },
        "selected":
        {
            "fg": "white",
            "bg": "blue"
        },
        "border":
        {
            "normal": "inherit",
            "focused": "inherit"
        }
    }

}
"""


class Theme(object):
    """Manage theme data."""

    _cache = {}

    @classmethod
    def loader(cls, fs):
        """Automatically add theme to context."""
        def load(context=None):
            if context is None:
                context = pilot.context
            name = context.get('.sys.site.theme', 'default')

            path = "{}.json".format(name)
            try:
                theme = cls.read(fs, path, context=context)
            except Exception as e:
                log.warning("unable to read theme file '%s' (%s)", path, text_type(e))

                if name != 'default':
                    return load('default')

                log.error("unable to load 'default' theme")
                theme = None

            return theme

        return load

    @classmethod
    def dummy_loader(cls, context):
        """Called when theme is not enabled."""
        log.warning('theme is not set -- add a theme value to your site settings')
        theme_json = DEFAULT
        hasher = hashlib.md5()
        hasher.update(theme_json.encode('utf-8'))
        theme_hash = hasher.hexdigest()

        theme_data = json.loads(theme_json)

        theme_data['_moya'] = {
            "path": None,
            "hash": theme_hash
        }
        return theme_data

    @classmethod
    def read(cls, fs, path, context=None):

        if context is None:
            context = Context()

        hasher = hashlib.md5()
        with fs.open(path, 'rt', encoding="utf-8") as f:
            theme_json = f.read()
            hasher.update(theme_json.encode('utf-8'))
            theme_hash = hasher.hexdigest()

            theme_data = json.loads(theme_json)

            theme_data['_moya'] = {
                "path": path,
                "hash": theme_hash
            }

        return theme_data
