from __future__ import unicode_literals
from __future__ import print_function

from ..elements.elementbase import Attribute
from ..tags.context import DataSetter
from ..template.rendercontainer import RenderContainer
from ..template.moyatemplates import Template
from ..logic import DeferNodeContents, EndLogic
from ..render import render_object
from ..response import MoyaResponse
from ..compat import py2bytes, text_type


from fs.errors import FSError


class ResolveTemplate(DataSetter):
    """Resolve a relative template and return a absolute path"""

    class Help:
        synopsis = "resolve a relative template path"

    path = Attribute("Template path", required=True)
    _from = Attribute("Application", type="application", required=False, default=None)

    def get_value(self, context):
        app = self.get_app(context)
        template_path = app.resolve_template(self.path(context))
        return template_path


class RenderTemplate(DataSetter):
    """Render a template"""

    class Help:
        synopsis = "render a template and store the result"

    template = Attribute("Template", type="template", required=True)
    withscope = Attribute("Use data from current scope?", default=False, type="boolean")
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
        with context.data_scope(value):
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
        response = MoyaResponse(charset=py2bytes('utf8'))
        if content_type:
            response.content_type = py2bytes(content_type)
        response.text = html
        raise EndLogic(response)


class RenderTemplateFS(DataSetter):
    """
    Render a template from a filesystem.

    This tag renders a template outside of the template filesystem.

    """

    class Help:
        synopsis = "render a template in a filesystem"

    fs = Attribute("Filesystem", required=True, type="expression")
    path = Attribute("Path to template")
    withscope = Attribute("Use data from current scope?", default=False, type="boolean")

    def logic(self, context):
        params = self.get_parameters(context)

        template_fs = self.archive.get_filesystem(params.fs)
        try:
            template_source = template_fs.gettext(params.path)
        except FSError as e:
            self.throw('render-template-fs.read-fail',
                       "failed to read '{}' from '{}'".format(params.path, template_fs),
                       error=text_type(e))

        template = Template(template_source, template_fs.desc(params.path), raw_path=params.path)
        template.parse(self)

        scope = {}
        if params.withscope:
            scope.update(context['.call'])
        params = {'app': context['.app']}
        params.update(self.get_let_map(context))

        engine = self.archive.get_template_engine("moya")
        html = engine.render_template(template, scope, **params)

        self.on_value(context, html)


class ServeTemplateFS(RenderTemplateFS):
    """
    Render and serve a template from a filesystem.

    See [tag]render-template[/tag].

    """

    content_type = Attribute("Mime Type", required=False, default=None)

    class Help:
        synopsis = """render and serve a template in a filesystem"""

    def on_value(self, context, html):
        content_type = self.content_type(context)
        response = MoyaResponse(charset=py2bytes('utf8'))
        if content_type:
            response.content_type = py2bytes(content_type)
        response.text = html
        raise EndLogic(response)
