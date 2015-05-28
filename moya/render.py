"""
The Moya Render protocol

"""
from __future__ import unicode_literals
from __future__ import print_function

from .compat import text_type, implements_to_string
from .html import escape

import json


@implements_to_string
class HTML(text_type):
    html_safe = True

    def __repr__(self):
        return "HTML(%s)" % super(HTML, self).__repr__()

    def __str__(self):
        return self


class Safe(text_type):
    html_safe = True


class Unsafe(text_type):
    html_safe = False


class RenderList(list):
    """A list of renderables"""

    def moya_render(self, archive, context, target, options):
        return render_objects(self, archive, context, target, options)


def is_renderable(obj):
    """Check if an object complies to the render protocol"""
    return hasattr(obj, 'moya_render')


def is_safe(obj):
    return getattr(obj, 'html_safe', False)


def render_object(obj, archive, context, target, options=None):
    """Render an object"""
    if hasattr(obj, 'moya_render'):
        if hasattr(obj, 'moya_render_targets') and target not in obj.moya_render_targets:
            rendered = text_type(obj)
        else:
            rendered = obj.moya_render(archive, context, target, options or {})
    elif target == "json":
        rendered = json.dumps(obj)
    elif target == "html.linebreaks":
        rendered = HTML("<br>\n".join(escape(text_type(obj)).splitlines()))
    else:
        if obj is None:
            rendered = ''
        else:
            rendered = obj
    if target in ('', 'html') and not getattr(rendered, 'html_safe', False):
        rendered = escape(rendered)
    return rendered


def render_objects(objects, archive, context, target, options=None, join="\n"):
    """Renders a sequence of objects and concatenates them together with carriage returns"""
    return HTML(join.join([render_object(obj, archive, context, target, options=options)
                for obj in objects]))


if __name__ == "__main__":
    text = HTML("<b>Hello</b>")
    print(repr(text))
