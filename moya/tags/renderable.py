from __future__ import unicode_literals
from __future__ import print_function

from ..elements.elementbase import Attribute
from ..tags.context import DataSetter
from ..template.rendercontainer import RenderContainer
from ..logic import DeferNodeContents, EndLogic
from ..render import render_object
from ..response import MoyaResponse
from ..compat import PY2, py2bytes


class RenderTemplate(DataSetter):
    """Render a template"""

    class Help:
        synopsis = "render a template and store the result"

    template = Attribute("Template", type="template", required=True)
    withscope = Attribute("Use current scope?", default=False, type="boolean")
    format = Attribute("Format to render", default="html", required=False)
    _from = Attribute("Application", type="application", required=False, default=None)

    def logic(self, context):
        params = self.get_parameters(context)
        app = self.get_app(context)
        template = app.resolve_template(params.template)
        value = RenderContainer.create(app,
                                       template=template)
        value.update(self.get_let_map(context))
        if params.withscope:
            value.update(context['.call'])
        context['_render'] = value
        with context.scope('_render'):
            yield DeferNodeContents(self)
        self.on_value(context, value)

    def on_value(self, context, value):
        html = render_object(value, self.archive, context, self.format(context))
        self.set_context(context, self.dst(context), html)


class ServeTemplate(RenderTemplate):
    """Render and serve a template"""

    content_type = Attribute("Mime Type", required=False, default=None)

    class Help:
        synopsis = """render and serve a template"""

    def on_value(self, context, value):
        content_type = self.content_type(context)
        html = render_object(value, self.archive, context, self.format(context))
        response = MoyaResponse(charset=b'utf8' if PY2 else 'utf8')
        if content_type:
            response.content_type = py2bytes(content_type)
        response.text = html
        raise EndLogic(response)
