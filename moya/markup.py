from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from .render import HTML
from . import html
from .compat import with_metaclass, implements_to_string, text_type
import postmarkup
import CommonMark


def get_installed_markups():
    return list(MarkupBaseMeta.markup_registry.keys())


class MarkupBaseMeta(type):
    markup_registry = {}

    def __new__(cls, name, base, attrs):
        new_class = type.__new__(cls, name, base, attrs)
        if name != "MarkupBase":
            name = getattr(new_class, 'name', name.lower().strip('_'))
            cls.markup_registry[name] = new_class
        return new_class


@implements_to_string
class MarkupBaseType(object):
    __metaclass__ = MarkupBaseMeta

    def __init__(self, markup_type, markup_options):
        self.markup_type = markup_type
        self.markup_options = markup_options
        self.create(markup_options)

    def __str__(self):
        return "<markup {}>".format(self.name)

    def create(self, options):
        pass

    @classmethod
    def get_processor(cls, name, markup_options):
        markup_class = MarkupBaseMeta.markup_registry[name]
        return markup_class(name, markup_options)

    def process(self, text, target, options):
        target = text_type(target or 'text')
        process_method = "process_" + target
        if hasattr(self, process_method):
            return getattr(self, process_method)(text, target, options)
        else:
            raise ValueError("Don't know how to render target '{}'".format(target))

    def escape(self, text):
        return text_type(text)

    def process_text(self, text, target, options):
        html_markup = self.process_html(text, target, options)
        return html.textilize(html_markup)

    def moya_render(self, archive, context, target, options):
        rendered = self.process(self.source, target, options)
        return rendered


class MarkupBase(with_metaclass(MarkupBaseMeta, MarkupBaseType)):
    pass


class TextMarkup(MarkupBase):
    name = "text"

    def process_html(self, text, target, options):
        return HTML(html.escape(text).replace('\n', '<br>'))


class HTMLMarkup(MarkupBase):
    name = "html"

    def process_html(self, text, target, options):
        return HTML(text)


class BBCodeMarkup(MarkupBase):
    name = "bbcode"

    def process_text(self, text, target, options):
        return postmarkup.strip_bbcode(text)

    def process_html(self, text, target, options):
        html = postmarkup.render_bbcode(text)
        return HTML(html)


# class MarkdownMarkup(MarkupBase):
#     name = "markdown"

#     def create(self, options):
#         if 'output_format' not in options:
#             options['output_format'] = 'html5'
#         self.markdown = markdown.Markdown(**options)

#     def escape(self, text):
#         return html.escape(text)

#     def process_html(self, text, target, options):
#         return HTML(self.markdown.convert(text))


class SummaryMarkup(MarkupBase):
    name = "summary"

    def process_html(self, text, target, options):
        return HTML(html.summarize(text, max_size=options.get('length', 100)))


class MarkdownMarkup(MarkupBase):
    name = "markdown"

    def create(self, options):
        self.parser = CommonMark.DocParser()
        self.renderer = CommonMark.HTMLRenderer()

    def process_html(self, text, target, options):
        ast = self.parser.parse(text)
        html = HTML(self.renderer.render(ast))
        return html


@implements_to_string
class Markup(object):
    html_safe = True

    def __init__(self, source, type, markup_options=None):
        self.source = source
        self.type = type
        if markup_options is None:
            markup_options = {}
        self.markup_options = markup_options
        try:
            self.markup_processor = MarkupBase.get_processor(self.type, markup_options)
        except KeyError:
            raise ValueError("No markup processor called '{}'".format(self.type))

    @classmethod
    def get_escape(cls, type, markup_options=None):
        try:
            markup_processor = MarkupBase.get_processor(type, markup_options)
        except KeyError:
            raise ValueError("No markup processor called '{}'".format(type))
        return markup_processor.escape

    @classmethod
    def sub(cls, type, context, text, markup_options=None):
        try:
            markup_processor = MarkupBase.get_processor(type, markup_options)
        except KeyError:
            raise ValueError("No markup processor called '{}'".format(type))
        return context.sub(text, markup_processor.escape)

    def __str__(self):
        return self.markup_processor.process(self.source, "text", None)

    def moya_render(self, archive, context, target, options):
        return self.markup_processor.process(self.source, target, options)
