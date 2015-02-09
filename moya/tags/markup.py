from ..markup import Markup, get_installed_markups
from ..elements.elementbase import Attribute
from ..tags.content import RenderBase

from textwrap import dedent


class _Markup(RenderBase):
    """Insert markup in to content"""

    class Help:
        synopsis = "insert markup in to content"

    type = Attribute("Markup type", required=False, default="bbcode", choices=get_installed_markups())
    source = Attribute("Markup source", required=False, default=None, type="expression")

    def logic(self, context):
        type = self.type(context)
        options = self.get_let_map(context)
        source_text = self.source(context) if self.has_parameter('source') else self.text
        text = self.source(context) or Markup.sub(type, context, source_text, options)
        markup = Markup(text, type, options)
        context['.content'].add_renderable(self._tag_name, markup)


class MarkupTag(RenderBase):

    source = Attribute("Markup source", required=False, default=None, type="expression")
    dedent = Attribute("De-dent source (remove common leading whitespace)?", type="boolean", default=True)

    class Help:
        undocumented = True

    def logic(self, context):
        options = self.get_let_map(context)
        source_text = self.source(context) if self.has_parameter('source') else self.text
        if not self.has_parameter('source') and self.dedent(context):
            source_text = dedent(source_text)
        sub_text = Markup.sub(self.markup, context, source_text, options)
        markup = Markup(sub_text, self.markup, options)
        context['.content'].add_renderable(self._tag_name, markup)


class BBCode(MarkupTag):
    """Add bbcode to content"""
    markup = "bbcode"

    class Help:
        synopsis = "add bbcode to content"


class Markdown(MarkupTag):
    """Add markdown to content"""
    markup = "markdown"

    class Help:
        synopsis = "add markdown to content"


class CommonMark(MarkupTag):
    """
    Add markdown to content.

    The output of this tag is similar to [tag]markdown[/tag], but uses [url http://commonmark.org/]CommonMark[/url] -- a standardized version of Markdown.

    """

    markup = "commonmark"

    class Help:
        synopsis = "add commonmark to content"
