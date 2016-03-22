from ..markup import Markup, get_installed_markups, get_markup_choices
from ..elements.elementbase import Attribute
from ..tags.content import RenderBase
from ..tags.context import DataSetter, LogicElement
from ..compat import text_type

from textwrap import dedent


class _Markup(RenderBase):
    """Insert markup in to content"""

    class Help:
        synopsis = "insert markup in to content"

    type = Attribute("Markup type", required=False, default="bbcode", choices=get_installed_markups())
    source = Attribute("Markup source", required=False, default=None, type="expression")

    def logic(self, context):
        type = self.type(context)
        if not Markup.supports(type):
            self.throw('markup.unsupported', "markup type '{}' is not supported".format(type))
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
        if not Markup.supports(self.markup):
            self.throw('markup.unsupported', "markup type '{}' is not supported".format(self.markup))
        options = self.get_let_map(context)
        source_text = self.source(context) if self.has_parameter('source') else self.text
        if not self.has_parameter('source') and self.dedent(context):
            source_text = dedent(source_text)
        sub_text = Markup.sub(self.markup, context, source_text, options)
        markup = Markup(sub_text, self.markup, options)
        context['.content'].add_renderable(self._tag_name, markup)


class ProcessMarkup(DataSetter):
    """Process a given markup in to text"""

    type = Attribute("Markup type", required=False, default="bbcode")
    src = Attribute("Markup source", required=False, default=None, type="expression")
    dst = Attribute("Destination", type="reference", default=None)

    class Help:
        synopsis = "markup text"

    def logic(self, context):
        type = self.type(context)
        if not Markup.supports(type):
            self.throw('markup.unsupported', "markup type '{}' is not supported".format(type))
        options = self.get_let_map(context)
        source_text = self.src(context) if self.has_parameter('src') else self.text
        if not isinstance(source_text, text_type):
            self.throw('bad-value.unsupported-type',
                       "the 'src' parameter should be a a string (not {})".format(context.to_expr(source_text)))

        text = self.src(context) or Markup.sub(type, context, source_text, options)
        markup = Markup(text, type, options)
        result = markup.process(self.archive, context)
        self.set_context(context, self.dst(context), result)


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


class GetMarkupTypes(DataSetter):
    """Get a list of all available Markup processors"""

    class Help:
        synopsis = "get supported markups"

    def get_value(self, context):
        return get_installed_markups()


class GetMarkupChoices(DataSetter):
    """Get a list of Markup processor choices, suitable for use in a [tag forms]select[/tag] tag."""

    class Help:
        synopsis = "get supported markups"

    def get_value(self, context):
        return get_markup_choices()


class MarkupInsert(LogicElement):
    """A callable invoked from Moya markup"""
    _moya_markup_insert = True

    class Help:
        synopsis = "insert code from markup"

    class Meta:
        is_call = True
