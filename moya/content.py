from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from .render import render_object, HTML, RenderList, is_renderable
from .containers import OrderedDict
from .html import escape
from . import interface
from .compat import implements_to_string, text_type, string_types, iteritems, iterkeys
from .tools import unique
from .errors import ContentError

from contextlib import contextmanager
from collections import defaultdict
from pprint import pprint


@implements_to_string
class IncludePath(object):
    def __init__(self, type, path, format, **options):
        self.type = type
        self.path = path
        self._format = format
        self._html = HTML(self._format.format(path=path))
        self.options = options

    def __eq__(self, other):
        return self._html == other._html

    def __repr__(self):
        return '<includepath {} "{}">'.format(self.type, self.path)

    def __str__(self):
        return self._html

    def moya_render(self, archive, context, target, options):
        return self._html


class NodeContextManager(object):

    def __init__(self, content):
        self.content = content

    def __enter__(self):
        self.content.push_node()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.content.pop_node()


class SectionContextManager(object):
    def __init__(self, content, section_name):
        self.content = content
        self.section_name = section_name

    def __enter__(self):
        section = self.content.get_section(self.section_name)
        self.content.push_section(section)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.content.pop_section()


@contextmanager
def push_content(context, content):
    """Context manager to push/pop content on to the content stack"""
    contentstack = context.set_new_call('.contentstack', list)
    contentstack.append(content)
    context['.content'] = content
    try:
        yield
    finally:
        contentstack.pop()
    context['.content'] = contentstack[-1] if contentstack else None


class Content(interface.AttributeExposer):
    """Hierarchical html content"""
    moya_render_targets = ["html"]
    __moya_exposed_attributes__ = ['td', 'sections', 'id']

    def __init__(self, app, template, td=None):
        self.app = app
        self.template = template
        if app and template:
            if isinstance(template, text_type):
                self.template = app.resolve_template(template)
            else:
                self.template = template
        self.td = td or {}
        self._include = defaultdict(RenderList)
        self._section_elements = defaultdict(list)
        self.sections = OrderedDict()
        #self.section_stack = [self.new_section("body", "base.html")]
        self.section_stack = []
        super(Content, self).__init__()

    def __repr__(self):
        if self.template:
            return '<content "{}">'.format(self.template)
        else:
            return '<content>'.format(self.template)

    @property
    def id(self):
        section = self.current_section
        return "{}_{}".format(section.name, section.id)

    def add_section_element(self, name, app, element, merge):
        self._section_elements[name].append((app, element, merge))

    def include(self, include_type, path):
        include_list = self._include[include_type]
        if path not in include_list:
            include_list.append(path)

    def include_css(self, path, format='<link href="{path}" rel="stylesheet" type="text/css">'):
        self.include('css', IncludePath('css', path, format))

    def push_section(self, section):
        self.section_stack.append(section)

    def pop_section(self):
        return self.section_stack.pop()

    @property
    def current_section(self):
        try:
            return self.section_stack[-1]
        except IndexError:
            raise ContentError("can't add content outside of a section",
                               diagnosis="Enclose content tags within a **&lt;section&gt;** tag")

    @property
    def in_section(self):
        return bool(self.section_stack)

    def __moyaconsole__(self, console):
        for section_name, section in self.sections.items():
            console.text('<section "%s"/>' % section_name)
            if section.td:
                console.obj(None, section.td)
            else:
                section.__moyaconsole__(console)

    def add_td(self, name, value):
        if self.in_section:
            self.current_section.add_td(name, value)
        else:
            self.td[name] = value

    def node(self):
        return NodeContextManager(self)

    def template_node(self, name, template, td=None, app=None):
        self.current_section.add_template(name, template, td, app=app)
        return NodeContextManager(self)

    def section(self, name):
        return SectionContextManager(self, name)

    def merge_td(self, td):
        for k in td:
            if k not in self.td:
                self.td[k] = td[k]

    def get_section(self, name):
        if name not in self.sections:
            self.new_section(name, None)
        return self.sections[name]

    def set_section(self, name):
        """Get, or create, a section"""
        self.current_section = self.sections[name]

    def merge(self, content):
        """Merge this content"""
        # Insert a content object, such as a form, and update sections / includes

        #self.app = content.app
        #self.merge_td(content.td)
        for k, v in iteritems(content._include):
            include_list = self._include[k]
            for item in v:
                if item not in include_list:
                    include_list.append(item)
        for section_name, section in iteritems(content.sections):
            self.get_section(section_name).merge(section, 'append')

    def merge_content(self, content):
        """Merge this content with another content object"""
        self.app = content.app
        self.merge_td(content.td)
        for k, v in iteritems(content._include):
            include_list = self._include[k]
            for item in v:
                if item not in include_list:
                    include_list.append(item)
        self.template = content.template or self.template

    def new_section(self, name, template, td=None, merge="append"):
        """Create a new section and make it current"""
        section = self.sections.get(name, None)
        if section is None:
            section = self.sections[name] = Section(template, td, name=name, merge_method=merge)
        else:
            section.template = section.template or template
            section.merge_method = merge
        return section

    def push_node(self):
        self.current_section.push_node()

    def pop_node(self):
        self.current_section.pop_node()

    def add_template(self, name, template, td=None, app=None):
        if app is not None:
            template = app.resolve_template(template, check=True)
        return self.current_section.add_template(name, template, td, app=app)

    def add_renderable(self, name, renderable):
        self.current_section.add_renderable(name, renderable)
        if hasattr(renderable, 'on_content_insert'):
            renderable.on_content_insert(self)

    def add_text(self, name, text):
        self.current_section.add_text(name, text)

    def add_markup(self, name, markup):
        self.current_section.add_markup(name, markup)

    def moya_render(self, archive, context, target, options):
        engine = archive.get_template_engine('moya')
        td = self.td.copy()
        td.update(sections=self.sections, include=self._include)

        if isinstance(self.template, text_type):
            template = self.app.resolve_template(self.template)
        else:
            template = self.template
        rendered = engine.render(template,
                                 td,
                                 base_context=context,
                                 app=self.app)

        return HTML(rendered)

    def print_tree(self):
        pprint(self.td)
        for name, section in self.sections.items():
            print('{%s "%s"}' % (name, self.template))
            if section.td:
                pprint(section.td)
            section.print_tree()


@implements_to_string
class Node(object):
    """A renderable node in the render tree"""
    def __init__(self, name):
        self.name = name
        self.section = None
        self.parent = None
        self.children = []
        self._groups = defaultdict(list)
        super(Node, self).__init__()

    def __str__(self):
        return "<node>"

    # def __getitem__(self, index):
    #     if isinstance(index, text_type):
    #         for child in self.children:
    #             if getattr(child, 'name', None) == index:
    #                 return child
    #         raise KeyError(index)
    #     return self.children[index]

    def add_child(self, node, group=None):
        node.parent = self
        self.children.append(node)
        if group is not None:
            self._groups[group].append(node)

    def moya_render(self, archive, context, target, options):
        return ''


@implements_to_string
class RootNode(Node):
    """A root dummy node"""
    def __init__(self):
        super(RootNode, self).__init__('root')

    def __str__(self):
        return "<root>"


@implements_to_string
class TemplateNode(Node):
    """Render a template"""
    def __init__(self, name, template, td=None, app=None):
        self.template = template
        self.td = td.copy() if td is not None else {}
        self.app = app
        self._rendered = None
        super(TemplateNode, self).__init__(name)
        self.td.update({'children': self.children,
                        'groups': self._groups})
        self.td['self'] = self

    def __str__(self):
        if is_renderable(self.template):
            return repr(self.template)
        else:
            return "<template-node '{}' '{}'>".format(self.name, self.template)

    __repr__ = __str__

    def __getitem__(self, key):
        if key == 'app':
            return self.td.get(key, self.app)
        return self.td[key]

    def get(self, key, default=None):
        return self.td.get(key, default)

    def update_template_data(self, td):
        self.td.update(td)

    def __contains__(self, key):
        return key in self.td

    def iterkeys(self):
        return iterkeys(self.td)

    def keys(self):
        return self.td.keys()

    def itervalues(self):
        return iteritems(self.td)

    def values(self):
        return self.td.values()

    def iteritems(self):
        return iteritems(self.td)

    def items(self):
        return self.td.items()

    def moya_render(self, archive, context, target, options):
        if self._rendered is not None:
            return self._rendered
        engine = archive.get_template_engine("moya")
        td = self.td

        if 'with' in options:
            td = td.copy()
            td.update(options['with'])

        if self.template is None:
            return ''

        if is_renderable(self.template):
            return render_object(self.template, archive, context, target, options)

        if isinstance(self.template, string_types):
            html = engine.render(self.template, td, base_context=context, app=self.app)
        else:
            html = engine.render_template(self.template, td, base_context=context, app=self.app)
        html = HTML(html)
        self._rendered = html
        return html


@implements_to_string
class TextNode(Node):
    """Plain text renderable"""
    def __init__(self, name, text):
        self.html = HTML(escape(text))
        super(TextNode, self).__init__(name)

    def __str__(self):
        return '<text "%s">' % self.name

    def moya_render(self, archive, context, target, options):
        return self.html


@implements_to_string
class MarkupNode(Node):
    """Plain text renderable"""
    def __init__(self, name, text):
        self.html = HTML(text)
        super(MarkupNode, self).__init__(name)

    def __str__(self):
        return '<markup "%s">' % self.name

    def moya_render(self, archive, context, target, options):
        return self.html


@implements_to_string
class RenderableNode(Node):
    def __init__(self, name, renderable):
        self.renderable = renderable
        super(RenderableNode, self).__init__(name)

    def __str__(self):
        return '<renderable %s "%s">' % (self.renderable, self.name)

    def moya_render(self, archive, context, target, options):
        return render_object(self.renderable, archive, context, target, options)


class TemplateSectionProxy(object):
    def __init__(self, section):
        self._section = section
        super(TemplateSectionProxy, self).__init__()

    @property
    def children(self):
        return self._section.generate_children_renderables()


class Section(object):

    moya_render_targets = ["html"]

    def __init__(self, template, td=None, name=None, merge_method="append"):
        self.template = template
        self.td = td or {}
        self.name = name
        self.root = RootNode()
        self.current_node = self.root
        self.render_stack = [self.root]
        self.id = 1
        self.merge_method = merge_method

    def __moyarepr__(self, context):
        return "<section '{}'>".format(self.name)

    def new_id(self):
        self.id += 1
        return self.id

    def add_node(self, node, group=None):
        if getattr(node, 'id', None) is None:
            node.id = "{name}{id}".format(name=self.name, id=self.new_id())
        self.current_node.add_child(node, group=group)
        node.section = self

    def push_node(self):
        self.current_node = self.current_node.children[-1]

    def pop_node(self):
        self.current_node = self.current_node.parent

    def add_template(self, name, template, td=None, app=None):
        node = TemplateNode(name, template, td, app=app)
        self.add_node(node)
        return node

    def add_text(self, name, text):
        node = TextNode(name, text)
        self.add_node(node)

    def add_markup(self, name, html):
        node = MarkupNode(name, HTML(html))
        self.add_node(node)

    def add_renderable(self, name, renderable):
        self.add_node(renderable)

    def append(self, value):
        self.add_node(value)

    def add_td(self, name, value):
        self.td[name] = value

    def merge(self, render_tree, merge_method=None):
        merge_method = merge_method or self.merge_method
        if merge_method == "inherit":
            merge_method = render_tree.merge_method
        if merge_method == "append":
            self.root.children.extend(render_tree.root.children)
        elif merge_method == "prepend":
            self.root.children[0:0] = render_tree.root.children
        elif merge_method == "replace":
            self.root.children[:] = render_tree.root.children
        else:
            raise NotImplementedError(merge_method)

    def print_tree(self, level=0):
        def recurse(node, level=0):
            indent = "  " * level
            print("%s%s" % (indent, node))
            if isinstance(node, Node):
                for child in node.children:
                    recurse(child, level + 1)
        recurse(self.root, level)

    def __moyaconsole__(self, console):
        def summarize(obj):
            text = text_type(obj).strip()
            if len(text) > 100 and not text.startswith('<'):
                text = text[:100] + '[...]'
            return text

        def recurse(node, level=1):
            indent = "  " * level
            console.text("%s%s" % (indent, summarize(node)))
            if hasattr(node, 'children'):
                for child in node.children:
                    recurse(child, level + 1)
        recurse(self.root, 1)

    def moya_render(self, archive, context, target, options):
        html = []
        nodes = self.root.children
        if options.get('unique', False):
            nodes = unique(nodes)

        for node in nodes:
            self.render_stack.append(node)
            try:
                node_html = render_object(node, archive, context, target, options)
            finally:
                self.render_stack.pop()
            html.append(node_html)
        return HTML(''.join(html))

    def generate_children_renderables(self):
        node = self.render_stack[-1]
        for node in getattr(node, 'children', ()):
            self.render_stack.append(node)
            try:
                yield node
            finally:
                self.render_stack.pop()

    def __iter__(self):
        render_node = self.render_stack[-1]
        for node in getattr(render_node, 'children', ()):
            self.render_stack.append(node)
            try:
                yield node
            finally:
                self.render_stack.pop()

    @property
    def template_self(self):
        return TemplateSectionProxy(self)


if __name__ == "__main__":
    content = Content(None, "blog.html")
    content["title"] = "Birthday"

    content.new_section("body", "posts.html")
    with content.section("body"):

        content.add_template("blog#list", "list.html")
        with content.node():
            content.add_template("blog#header", "header")
            content.add_template("blog#post", "post")
            with content.node():
                content["posts"] = 2
                content.add_template("blog#title", "title")
                content.add_template("blog#body", "body")
            content.add_template("#", "post")
            content.add_template("#", "footer")

    content.new_section("sidebar", "sidebar.html")

    with content.section("sidebar"):
        content["numposts"] = 10
        content.add_template("blog#recentposts", "recentposts")
        content.add_template("blog#tags", "tags")

    content.print_tree()
