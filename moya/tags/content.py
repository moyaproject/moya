from __future__ import unicode_literals
from __future__ import print_function

from ..elements.elementbase import Attribute, LogicElement
from ..tags.context import ContextElementBase, DataSetter
from ..render import HTML, is_renderable, Unsafe, render_object, is_safe
from ..context.dataindex import makeindex
from .. import logic
from .. import errors
from ..html import escape
from ..console import Console
from ..content import Content, Section, IncludePath
from ..tools import url_join, textual_list
from ..context.missing import is_missing
from ..markup import Markup, get_installed_markups
from ..template import Template as MoyaTemplate
from ..compat import string_types, text_type

from collections import defaultdict


class Renderable(object):
    moya_render_targets = ["html"]


class TemplateRenderable(Renderable):
    moya_safe = True

    def __init__(self, template, td):
        self.template = template
        self.td = td
        self.children = []

    def moya_render(self, archive, context, target, options):
        engine = archive.get_template_engine("moya")
        template = self.template
        if isinstance(template, string_types):
            html = engine.render(template, self.td, base_context=context)
        else:
            html = engine.render_template(template, self.td, base_context=context)
        return HTML(html)

    def add_renderable(self, renderable):
        self.children.append(renderable)


class ContentElementMixin(object):

    def resolve_template(self, app, template, element=None):
        """Get template path relative to templates filesystem"""
        if element is None:
            element = self
        if template is None:
            return None
        template_engine = self.archive.get_template_engine()

        _template = app.resolve_template(template)
        if not template_engine.exists(_template):
            raise errors.ContentError("missing template '{}'".format(template),
                                      element=element,
                                      diagnosis="You can check what templates are installed with **moya fs templates --tree**.")
        return _template

    def resolve_templates(self, app, templates, element=None):
        """Get first template path that exists"""
        if templates is None:
            return None
        if element is None:
            element = self

        template_exists = self.archive.get_template_engine().exists
        for _template in templates:
            template = app.resolve_template(_template)
            if template_exists(template):
                return template

        if len(templates) == 1:
            raise errors.ContentError("missing template '{}'".format(templates[0]),
                                      element=element,
                                      diagnosis="You can check what templates are installed with **moya fs templates --tree**.")
        else:
            raise errors.ContentError("missing templates ".format(textual_list(template)),
                                      element=element,
                                      diagnosis="You can check what templates are installed with **moya fs templates --tree**.")

    def push_content_frame(self, context, content):
        content_stack = context.set_new_call(".contentstack", list)
        content_stack.append(content)
        context['.content'] = content
        template_data_index = makeindex('.contentstack', len(content_stack) - 1, 'td')
        context.push_scope(template_data_index)

    def pop_content_frame(self, context):
        context.pop_scope()
        stack = context['.contentstack']
        value = stack.pop()
        if stack:
            context['.content'] = stack[-1]
        else:
            del context['.content']
        return value

    def get_content(self, context):
        content_stack = context['.contentstack']

        if not content_stack:
            raise logic.FatalMoyaException("content.content-not-found",
                                           "Content not found (did you forget the <content> tag)?")

        return content_stack[-1]

    def generate_content(self, context, element_ref, app, td):
        app, element = self.get_element(element_ref, app or None)

        merge_content = []
        for content_app, content_element in element.get_extends_chain(context, app=app):
            templates = content_element.templates(context)
            template = self.resolve_templates(content_app, templates, content_element) if content_app else templates[0]
            content = Content(content_app, template, td=td)
            merge_content.append(content)

            if content_element.has_children:
                self.push_content_frame(context, content)
                try:
                    self.push_defer(context, content_app)
                    try:
                        yield logic.DeferNodeContents(content_element)
                    finally:
                        self.pop_defer(context)
                finally:
                    self.pop_content_frame(context)

        sections = defaultdict(list)

        for _content in merge_content:
            for k, v in _content._section_elements.items():
                sections[k].extend(v)

        for section, elements in list(sections.items()):
            new_elements = []
            merge = 'replace'
            for _app, _element, _merge in elements:
                if _merge != 'inherit':
                    merge = _merge
                if merge == 'replace':
                    new_elements[:] = [(_app, _element, merge)]
                elif merge == 'append':
                    new_elements.append((_app, _element, merge))
                elif merge == 'prepend':
                    new_elements.insert(0, (_app, _element, merge))
                else:
                    raise ValueError('unknown merge value ({})'.format(merge))

            sections[section][:] = new_elements

        content = merge_content[0]
        for extended_content in merge_content[1:]:
            content.merge_content(extended_content)

        for section, elements in sections.items():
            for app, section_el, merge in elements:
                self.push_content_frame(context, content)
                try:
                    self.push_defer(context, app)
                    try:
                        for el in section_el.generate(context, content, app, merge):
                            yield el
                    finally:
                        self.pop_defer(context)
                finally:
                    self.pop_content_frame(context)

        if content.template is None:
            content.template = app.default_template
        if not content.template:
            raise errors.ElementError('content has no template',
                                      element=self,
                                      diagnosis="You can specify a template on the &lt;content&gt; definition")
        context['_content'] = content


class ContentElement(ContextElementBase):
    """
    Begin a [link content]content[/link] definition.

    Content is a high level description of a page.

    """

    class Help:
        synopsis = "define content"
        example = """
        <content libname="content.crew.manifest">
            <title>Crew Manifest</title>
            <section name="content">
                <for src="crew" dst="character">
                    <moya:crew character="character"/>
                </form>
            </section>
            <section name="footer">
                <markdown>Brought to you by **Moya**.</markdown>
            </section>
        </content>

        """

    template = Attribute("Template name(s)", type="templates", required=False, default=None, map_to="templates")
    extends = Attribute("Extend content element", type="elementref")
    final = Attribute("Stop extending with this content element?", type="boolean", default=False)

    preserve_attributes = ['template', 'extends', '_merge']

    class Meta:
        tag_name = "content"
        translate = False

    def get_extends_chain(self, context, app=None):
        element_refs = set()
        app = app or context.get('.app', None)
        node = self
        nodes = [(app, node)]
        extends_ref = node.extends
        while extends_ref:
            if node.final:
                break
            element_refs.add(extends_ref)
            node_app, node = self.document.detect_app_element(context, extends_ref, app=app)
            app = node_app or app
            if node is None:
                break
            nodes.append((app, node))
            extends_ref = node.extends
            if extends_ref in element_refs:
                raise errors.ContentError("element '{}' has already been extended".format(extends_ref),
                                          element=self,
                                          diagnosis="Check the 'extends' attribute in your content tags.")

        if not node.final:
            base_content = context.get('.sys.site.base_content')
            if base_content:
                app, node = self.document.get_element(base_content,
                                                      lib=node.lib)
                nodes.append((app, node))

        chain = nodes[::-1]
        # for app, node in chain:
        #     print (repr(app), repr(node), node.template)
        return chain

    def post_build(self, context):
        #self.template = self.template(context)
        self.extends = self.extends(context)
        self.final = self.final(context)


class SectionElement(LogicElement, ContentElementMixin):
    """
    Defines a section container for content. A [i]section[/i] is a top level container for content, and is used to break up the content in to function groups, which may be rendered independently. For example, here is a content definition with two sections; 'body' and 'sidebar':

    [code xml]
    <content libname="content.front" template="front.html">
        <section name="body">
            <!-- main body content goes here -->
        </section>
        <section name="sidebar">
            <!-- sidebar content here -->
        </section>
    </content>
    [/code]

    The template for the above content would render the sections with the [link templates#render]{% render %}[/link] template tag, For example:

    [code moyatemplate]
    <html>
        <body>
            <div id="sidebar>
            {% render sections.sidebar %}
            </div>
            <h1>Content example</h1>
            {% render sections.body %}
        </body>
    </html>
    [/code]
    """

    class Help:
        synopsis = "create a content section"

    name = Attribute("The name of the section", required=True)
    template = Attribute("Template", required=False, default=None)
    merge = Attribute("Merge method", default="inherit", choices=["inherit", "append", "prepend", "replace"])

    class Meta:
        tag_name = "section"

    def logic(self, context):
        name, template, merge = self.get_parameters(context, 'name', 'template', 'merge')
        content = self.get_content(context)
        app = self.get_app(context)
        content.add_section_element(name, app, self, merge)

    def generate(self, context, content, app, merge):
        name, template = self.get_parameters(context, 'name', 'template')
        content.new_section(name, app.resolve_template(template), merge=merge)
        with content.section(name):
            yield logic.DeferNodeContents(self)


def make_default_section(name):
    _name = name

    class _Section(SectionElement):
        __moya_doc__ = """
            Define a content [tag]section[/tag] called '{name}'.

            This is a shortcut for the following:
            [code xml]
            <section name="{name}">
                <!-- content tags here... -->
            </section>
            [/code]""".format(name=_name)

        class Help:
            synopsis = "add a '{}' content section".format(_name)
            example = """
            <section-{}>
            <!-- content tags here... -->
            </section>
            """.format(_name)

        class Meta:
            tag_name = "section-" + _name

        name = Attribute("The name of the section", required=False, default=_name)

    return _Section

SectionHead = make_default_section('head')
SectionCss = make_default_section('css')
SectionIncludecss = make_default_section('includecss')
SectionJs = make_default_section('js')
SectionJsfoot = make_default_section('jsfoot')
SectionIncludejs = make_default_section('includejs')
SectionBody = make_default_section('body')
SectionContent = make_default_section('content')
SectionFooter = make_default_section('footer')


class Node(LogicElement, ContentElementMixin):
    """
    Create a template node in a content definition. A node is essentially a reference to a template with associated data. Here's an example of a content definition containing a template node:

    [code xml]
    <content libname="content.example" template="front.html">
        <section name="body">
            <node template="newscontainer.html" let:style="splash"/>
                <html:p>${news}</html:p>
            </node>
        </section>
    </content>
    [/code]

    Here's what newscontainer.html might look like. Note the use of [link templates#children]{% children %}[/link] which will render the content contained inside a node:

    [code moyatemplate]
    <div style="${style}">
        <h3>The Latest News</h3>
        {% children %}
    </div>
    [/code]
    """

    class Help:
        synopsis = """creates a template node in content"""

    template = Attribute("Template", type="template", required=False, default=None)
    withscope = Attribute("Is current context when rendering template", type="boolean", default=False, required=False)
    _from = Attribute("Application", type="application", required=False, default=None)
    ifexists = Attribute("Skip if the template can not be found", type="boolean", required=False, default=False)

    def logic(self, context):
        template, withscope, ifexists = self.get_parameters(context, 'template', 'withscope', 'ifexists')
        content = self.get_content(context)
        app = self.get_app(context)
        template = app.resolve_template(template)

        if ifexists:
            engine = self.archive.get_template_engine("moya")
            if not engine.exists(template):
                return

        if withscope:
            td = {}
            td.update(context.capture_scope())
        else:
            td = self.get_let_map(context)
        content.add_template("node", template, td, app=app)
        if self.has_children:
            with content.node():
                yield logic.DeferNodeContents(self)


class ScopeNode(Node):
    """
    Create a template node that uses the current scope as the template data.

    This node is identical to [tag]node[/tag], with the [c]withscope[/c] attribute set to [c]yes[/c].

    """

    class Help:
        synopsis = """creates a template node using the current scope"""
    withscope = Attribute("Is current context when rendering template", type="boolean", default=True, required=False)


class RenderBase(LogicElement):
    obj = Attribute("Object to render", type="index")

    class Help:
        undocumented = True

    class Meta:
        translate = True

    def render_children(self, context):
        for child in self.children(element_class="renderable"):
            pass

    def include_css(self, context, media, app, path):
        if isinstance(app, text_type):
            app = self.archive.get_app_from_lib(app)
        path = self.archive.get_media_url(context, app, media, path)
        content = context['.content']
        content.include('css', IncludePath('css', path, IncludeCSS.format))


class RenderContent(DataSetter, ContentElementMixin):
    """Render content"""

    class Help:
        synopsis = "render content"

    class Meta:
        is_call = True

    content = Attribute("Reference to renderable content", type="elementref", required=False, default=None)
    _from = Attribute("Application", type="application", required=False, default=None)
    withscope = Attribute("Use current scope?", default=False, type="boolean")
    template = Attribute("Template", required=False, default=None)

    def logic(self, context):
        (content,
         withscope,
         template,
         dst) = self.get_parameters(context,
                                    'content',
                                    'withscope',
                                    'template',
                                    'dst')
        app = self.get_app(context)
        template = app.resolve_template(template)
        if withscope:
            scope = context['.call']
        let = self.get_let_map(context)
        td = {}
        if self.has_children:
            call = self.push_funccall(context)
            try:
                yield logic.DeferNodeContents(self)
            finally:
                self.pop_funccall(context)

            args, kwargs = call.get_call_params()
            if withscope:
                new_kwargs = scope
                new_kwargs.update(kwargs)
                kwargs = new_kwargs
            td.update(kwargs)
        td.update(let)

        for defer in self.generate_content(context, content, app, td=td):
            yield defer

        content_obj = context['_content']

        result = render_object(content_obj, self.archive, context, "html")
        self.set_context(context, dst, result)


class ServeContent(LogicElement, ContentElementMixin):
    """Render content and immediately serve it. Note that this tag will stop processing any more logic code."""

    class Help:
        synopsis = "render and serve content"
        example = """
        <serve-content content="#content.front" let:date=".now"/>

        """

    content = Attribute("Reference to renderable content", type="elementref", required=False, default=None)
    _from = Attribute("Application", type="application", required=False, default=None)
    withscope = Attribute("Use current scope?", default=False, type="boolean")
    template = Attribute("Template", required=False, default=None)

    class Meta:
        is_call = True

    def logic(self, context):
        content, withscope, template = self.get_parameters(context,
                                                           'content',
                                                           'withscope',
                                                           'template')
        app = self.get_app(context)
        template = app.resolve_template(template)
        if withscope:
            scope = context['.call']
        let = self.get_let_map(context)
        td = {}
        if self.has_children:
            call = self.push_funccall(context)
            try:
                yield logic.DeferNodeContents(self)
            finally:
                self.pop_funccall(context)

            args, kwargs = call.get_call_params()
            if withscope:
                new_kwargs = scope
                new_kwargs.update(kwargs)
                kwargs = new_kwargs
            td.update(kwargs)
        td.update(let)

        for defer in self.generate_content(context, content, app, td=td):
            yield defer
        context.copy('_content', '_return')

        raise logic.Unwind()


class Title(LogicElement):
    """Set the title for content. This tag simply sets a value called [c]title[/c] on the context, which can be rendered in a templates. Here's an example:

    [code xml]
    <content libname="content.front" template="front.html">
        <title>Welcome!<title>
    </content>
    [/code]

    A reference to [c]title[/c] would appear somewhere in the template associated with the content. For example:

    [code moyatemplate]
    <html>
       <head>
           <title>${title}</title>
        </head>
        <body>
            {% render sections.body %}
        </body>
    </html>
    [/code]
    """

    class Help:
        synopsis = "set content title"

    class Meta:
        translate = True

    def logic(self, context):
        context['title'] = context.sub(self.text)


class SimpleRenderable(Renderable):
    moya_safe = True

    class Help:
        undocumented = True

    def __init__(self, format_string, **kwargs):
        self.html = format_string.format(**kwargs)

    def __repr__(self):
        html = self.html
        if len(self.html) > 50:
            html = html[:50] + "[...]"
        return '<SimpleRenderable "%s">' % html

    def moya_render(self, archive, context, target, options):
        return HTML(self.html)


class MediaURL(DataSetter):
    """Get URL to media"""

    class Help:
        synopsis = "get a URL to media"

    path = Attribute("Path in media")
    media = Attribute("Media name", required=False, default='media')
    _from = Attribute("Application containing the media", type="application", default=None)
    dst = Attribute("Destination to store media URL", required=False, type="reference")

    def logic(self, context):
        params = self.get_parameters(context)
        app = self.get_app(context)
        media_path = self.archive.get_media_url(context, app, params.media)
        url = url_join(media_path, params.path)
        self.set_context(context, params.dst, url)


class IncludeCSS(LogicElement, ContentElementMixin):
    """
    Add a CSS path to be included in the content. The list of paths will be added to a value called [c]include[/c] when the template is rendered. Here's an example:

    [code xml]
    <content libname="content.front" template="front.html">
        <include-css path="css/news.css" />
    </content>
    [/code]

    The CSS paths can be rendered in a template as follows:

    [code moyatemplate]
    {% render include.css %}
    [/code]

    """

    class Help:
        synopsis = """include CSS with content"""

    type = Attribute("Type of link", required=False, default="css")
    media = Attribute("Media name", required=False, default='media')
    path = Attribute("Path to CSS", required=False, default=None)
    _from = Attribute("Application", type="application", default=None)
    url = Attribute("External URL", required=False, default=None)

    class Meta:
        one_of = [('path', 'url')]

    format = """<link href="{path}" rel="stylesheet" type="text/css">"""

    def logic(self, context):
        params = self.get_parameters(context)
        content = self.get_content(context)
        app = self.get_app(context)
        if params.url:
            path = params.url
        else:
            if params.path.startswith('/'):
                path = params.path
            else:
                media_path = self.archive.get_media_url(context, app, params.media)
                path = url_join(media_path, params.path)
        content.include(params.type, IncludePath(params.type, path, self.format))


class IncludeJS(IncludeCSS):
    """
    Like [tag]include-css[/tag], but inserts a link to a JS file.

    The JS files may be inserted in to the template as follows:

    [code moyatemplate]
    {% render include.js %}
    [/code]

    This is equivalent to the following:

    [code moyatemplate]
    {%- for include in include.js %}
    <script type="text/javascript" href="${include.path}"/>
    {%- endfor %}
    [/code]

    """

    class Help:
        synopsis = """include a JS file in content"""

    type = Attribute("Type of link", required=False, default="js")
    # media = Attribute("Media name", required=False, default='media')
    # path = Attribute("Path to JS", required=False, default=None)
    # _from = Attribute("Application", type="application", default=None)
    format = """<script src="{path}"></script>"""


class RenderProxy(object):

    def __init__(self, obj, td, target):
        self.obj = obj
        self.td = td
        self.target = target
        if hasattr(obj, 'moya_render_targets'):
            self.moya_render_targets = obj.moya_render_targets
        if hasattr(obj, 'html_safe'):
            self.html_safe = obj.html_safe

    def on_content_insert(self, context):
        if hasattr(self.obj, 'on_content_insert'):
            return self.obj.on_content_insert(context)

    def moya_render(self, archive, context, target, options):
        if hasattr(self.obj, 'moya_render'):
            options['with'] = self.td
            rendered = self.obj.moya_render(archive, context, self.target or target, options)
        else:
            rendered = render_object(self.obj, archive, context, self.target)
        return rendered


class Render(DataSetter, ContentElementMixin):
    """
    Render a [i]renderable[/i] object.

    """

    class Help:
        synopsis = "render an object in content"
        example = """
        <render src="form" />
        """

    src = Attribute("Object to render", required=False, type="expression", missing=False)
    dst = Attribute("Destination to store rendered content", required=False, type="reference")
    target = Attribute("Render target", required=False, default="html")

    def logic(self, context):
        content_container = context.get('.content', None)
        src, dst, target = self.get_parameters(context,
                                               'src',
                                               'dst',
                                               'target')
        td = self.get_let_map(context)
        if src is None:
            section = Section(None, td=td, name=self.libid)
            self.push_content_frame(context, section)
            try:
                yield logic.DeferNodeContents(self)
            finally:
                self.pop_content_frame(context)
            obj = section
        else:
            obj = src

        if not is_renderable(obj) and not is_safe(obj):
            obj = Unsafe(obj)

        if content_container is not None:
            content_container.add_renderable(self._tag_name, RenderProxy(obj, td, target))
        else:
            rendered = render_object(obj, self.archive, context, target)
            self.set_context(context, dst, rendered)


class RenderAll(DataSetter, ContentElementMixin):
    """
    Render a sequence of renderable objects.
    """

    class Help:
        synopsis = "render a sequence of renderable objects"

    src = Attribute("Object to render", required=False, type="expression")
    dst = Attribute("Destination to store rendered content", required=False, type="reference")
    target = Attribute("Render target", required=False, default="html")

    def logic(self, context):
        content_container = context.get('.content', None)
        src, dst, target = self.get_parameters(context,
                                               'src',
                                               'dst',
                                               'target')

        try:
            obj_iter = iter(src)
        except:
            self.throw('render-all.not-a-sequence',
                       'src is not a sequence',
                       diagnosis="Moya was unable to iterate over {}".format(context.to_expr(src)))

        for obj in obj_iter:
            if not is_renderable(obj) and not is_safe(obj):
                obj = Unsafe(obj)
            if content_container is not None:
                content_container.add_renderable(self._tag_name, obj)
            else:
                rendered = render_object(obj, self.archive, context, target)
                self.set_context(context, dst, rendered)


class Template(RenderBase):

    markup = Attribute("Markup", required=False, default="html", choices=get_installed_markups)

    def finalize(self, context):
        self.template = MoyaTemplate(self.text, self._location)

    def logic(self, context):
        rendered_content = self.template.render(context)
        markup = Markup(rendered_content, self.markup(context))
        context['.content'].add_renderable(self._tag_name, markup)


class Raw(RenderBase):
    #name = Attribute("Template name of the text")

    def logic(self, context):
        context['.content'].add_renderable(self._tag_name, HTML(context.sub(self.text)))


class Wrap(RenderBase):
    """Wrap content between two templates"""

    head = Attribute("head template")
    tail = Attribute("tail template")
    _from = Attribute("Application", type="application", required=False, default=None)

    def logic(self, context):
        params = self.get_parameters(context)
        td = self.get_let_map(context)
        content = context['.content']
        app = self.get_app(context)

        head_template = app.resolve_template(params.head)
        tail_template = app.resolve_template(params.tail)

        content.add_template('head', head_template, td)
        yield logic.DeferNodeContents(self)
        content.add_template('tail', tail_template, td)


class DefaultMarkup(RenderBase):
    """Use default markup if a value is None or missing"""

    class Help:
        synopsis = "use default markup for missing values"

    value = Attribute("Value", required=True, type="expression")
    default = Attribute("Default", required=False, default="&ndash;")

    def logic(self, context):
        value = self.value(context)
        if is_missing(value) or value is None:
            context['.content'].add_renderable(self._tag_name, HTML(self.default(context)))
        else:
            yield logic.DeferNodeContents(self)


class JS(RenderBase):
    """Insert Javascript content.

    Here's an example:

    [code xml]
    <!-- must be inside a content definition -->
    <js>alert("Ready for takeoff!);</js>
    [/code]

    This would render the following:

    [code moyatemplate]
    <script type="text/javascript">
        alert("Ready for takeoff!);
    </script>
    [/code]

    """

    class Help:
        synopsis = "insert Javascript content"

    class Meta:
        translate = False

    section = Attribute("Section to add script to", required=False, default="js")

    def logic(self, context):
        section = self.section(context)
        js = context.sub(self.text)
        html = """<script type="text/javascript">{}</script>\n""".format(js)
        context['.content'].get_section(section).add_renderable(self._tag_name, HTML(html))


class CSS(RenderBase):
    """
    This content tag creates a [c]<style>[/c] element in html, with the enclosed text.

    It is generally preferable to use [tag]include-css[/tag], but this tag can be useful to insert dynamically generated CSS.

    """
    section = Attribute("Section to add CSS tag to", required=False, default="css")

    class Help:
        synopsis = "add a CSS to content"
        example = """
        <css>
            .character.rygel
            {
                font-weight:bold
            }
        </css>
        """

    class Meta:
        translate = False

    def logic(self, context):
        section = self.section(context)
        css = context.sub(self.text)
        html = """<style type="text/css">\n%s\n</style>\n""" % css.strip()
        context['.content'].get_section(section).add_renderable(self._tag_name, HTML(html))


class Text(RenderBase):

    _ignore_skip = True

    def logic(self, context):
        text = self.lib.translate(context, self.text)
        text = escape(context.sub(text))
        html = HTML(text or ' ')
        context['.content'].add_renderable(self._tag_name, html)


class ConsoleRender(RenderBase):
    """Render an object as terminal output. Useful as a debugging aid to quickly render an object."""
    obj = Attribute("Object to render", type="expression", required=True)

    def logic(self, context):
        obj = self.obj(context)
        c = Console(nocolors=False, text=False, width=120, html=True, unicode_borders=False)
        text = c.obj(context, obj).get_text()
        html = '<div class="moya-console">{}</div>'.format(text)
        context['.content'].add_renderable(repr(obj), HTML(html))
        self.include_css(context, "media", 'moya.debug', 'css/debug.css')
