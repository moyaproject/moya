from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from .render import HTML, render_object
from . import html
from .compat import with_metaclass, implements_to_string, text_type
from .console import Console
from .errors import MarkupError, LogicError, ElementNotFoundError
from .content import Content
from .context.dataindex import makeindex

import postmarkup
import CommonMark
import io
from bs4 import BeautifulSoup

import logging
log = logging.getLogger('moya.runtime')

def get_installed_markups():
    """Get a list of identifiers for installed markups"""
    return list(MarkupBaseMeta.markup_registry.keys())


def get_markup_choices():
    """Get a choices list for installed markups"""
    choices = [(markup.name, markup.title)
               for markup in MarkupBaseMeta.markup_registry.values()
               if markup.choice and markup.title is not None]
    choices.sort(key=lambda m: m[1].lower(), reverse=True)
    return choices


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
    title = None
    choice = False

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

    def process(self, archive, context, text, target, options):
        target = text_type(target or 'text')
        process_method = "process_" + target
        if hasattr(self, process_method):
            return getattr(self, process_method)(archive, context, text, target, options)
        else:
            raise MarkupError("don't know how to render target '{}'".format(target))

    def escape(self, text):
        return text_type(text)

    def process_text(self, archive, context, text, target, options):
        html_markup = self.process_html(archive, context, text, target, options)
        return html.textilize(html_markup)

    def moya_render(self, archive, context, target, options):
        rendered = self.process(archive, context, self.source, target, options)
        return rendered


class MarkupBase(with_metaclass(MarkupBaseMeta, MarkupBaseType)):
    title = None  # Human readable title text
    choice = True  # True if the markup should be included in list in the UI


class TextMarkup(MarkupBase):
    name = "text"
    title = "Text (plain, escaped)"

    def process_html(self, archive, context, text, target, options):
        if options.get('linkify', False):
            return HTML(html.linkify(text))
        else:
            return HTML(html.escape(text).replace('\n', '<br>'))


class HTMLMarkup(MarkupBase):
    name = "html"
    title = "HTML (raw unescaped)"

    def process_html(self, archive, context, text, target, options):
        return HTML(text)


class BBCodeMarkup(MarkupBase):
    name = "bbcode"
    title = "BBCode (Postmarkup renderer)"

    def process_text(self, archive, context, text, target, options):
        return postmarkup.strip_bbcode(text)

    def process_html(self, archive, context, text, target, options):
        html = postmarkup.render_bbcode(text)
        return HTML(html)


class SummaryMarkup(MarkupBase):
    name = "summary"

    def process_html(self, archive, context, text, target, options):
        return HTML(html.summarize(text, max_size=options.get('length', 100)))


class MarkdownMarkup(MarkupBase):
    name = "markdown"
    title = "Markdown (CommonMark variety)"

    def create(self, options):
        self.parser = CommonMark.DocParser()
        self.renderer = CommonMark.HTMLRenderer()

    def process_html(self, archive, context, text, target, options):
        ast = self.parser.parse(text)
        html = HTML(self.renderer.render(ast))
        return html


class MoyaMarkup(MarkupBase):
    name = "moya"
    title = "Raw HTML + moya psuedo tags"
    choice = False

    def create(self, options):
        from .template import Template
        self.template = Template('<b>moya</b>{% render sections._widget %}')

    def process_html(self, archive, context, text, target, options):
        soup = BeautifulSoup(text, 'html.parser')
        for el in soup.find_all('moya'):

            insert_ref = el.attrs['insert']
            params = {k.split('-', 1)[-1]: v for k, v in el.attrs.items()
                      if k.startswith('data-')}

            app = context.get('.app', None)

            try:
                _app, insert_el = archive.get_element(insert_ref, app=app)
            except ElementNotFoundError as e:
                log.warning("markup insert element '{}' was not found".format(insert_ref))
                if context['.debug']:
                    c = Console(text=True)
                    c.obj(context, e)
                    replace_markup = '<pre class="moya-insert-error"><code>{}</code></pre>'.format(html.escape(c.get_text()))
                else:
                    replace_markup = "<!-- insert failed, see logs -->"
                new_el = BeautifulSoup(replace_markup, 'html.parser')
                el.replace_with(new_el)
                continue

            if not getattr(insert_el, '_moya_markup_insert', False):
                msg = '{} is not safe for markup insertion'.format(html.escape(insert_el))
                log.warning(msg)
                if context['.debug']:
                    new_el = BeautifulSoup('<pre class="moya-insert-error"><code>{}</code></pre>'.format(msg), 'html.parser')
                else:
                    new_el = BeautifulSoup('<!-- insert invalid -->', 'html.parser')
                el.replace_with(new_el)
                continue

            insert_callable = archive.get_callable_from_element(insert_el, app=_app)

            try:
                replace_markup = insert_callable(context, **params)
            except LogicError as e:
                from moya import pilot
                if context['.debug']:
                    c = Console(text=True)
                    c.obj(context, e)
                    replace_markup = '<pre class="moya-insert-error"><code>{}</code></pre>'.format(html.escape(c.get_text()))
                else:
                    replace_markup = "<!-- insert failed, see logs -->"
                pilot.console.obj(context, e)
            except Exception as e:
                log.exception('insert markup failed')
                replace_markup = "<!-- insert failed, see logs -->"

            new_el = BeautifulSoup(replace_markup, 'html.parser')
            el.replace_with(new_el)
        return HTML(text_type(soup))


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
            raise MarkupError("no markup processor called '{}'".format(self.type))

    @classmethod
    def get_escape(cls, type, markup_options=None):
        try:
            markup_processor = MarkupBase.get_processor(type, markup_options)
        except KeyError:
            raise MarkupError("no markup processor called '{}'".format(type))
        return markup_processor.escape

    @classmethod
    def sub(cls, type, context, text, markup_options=None):
        try:
            markup_processor = MarkupBase.get_processor(type, markup_options)
        except KeyError:
            raise MarkupError("no markup processor called '{}'".format(type))
        return context.sub(text, markup_processor.escape)

    @classmethod
    def supports(cls, name):
        return name in MarkupBaseMeta.markup_registry

    def __str__(self):
        return self.source
        return self.markup_processor.process(self.source, "text", None)

    def moya_render(self, archive, context, target, options):
        return self.markup_processor.process(archive, context, self.source, target, options)

    def process(self, archive, context, target="html", **options):
        return self.markup_processor.process(archive, context, self.source, target, options)
