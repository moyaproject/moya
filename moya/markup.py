from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from .render import HTML
from . import html
from .compat import with_metaclass, implements_to_string, text_type
from .console import Console
from .errors import MarkupError, LogicError, ElementNotFoundError


import postmarkup
import CommonMark

from lxml.cssselect import CSSSelector
from lxml.html import tostring, fromstring, fragment_fromstring

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
        self.parser = CommonMark.Parser()
        self.renderer = CommonMark.HtmlRenderer()

    def process_html(self, archive, context, text, target, options):
        ast = self.parser.parse(text)
        html = HTML(self.renderer.render(ast))
        return html


class MoyaMarkup(MarkupBase):
    name = "moya"
    title = "Raw HTML + moya psuedo tags"
    choice = False

    _selector = CSSSelector('moya')

    def create(self, options):
        from .template import Template
        self.template = Template('<b>moya</b>{% render sections._widget %}')

    def process_html(self, archive, context, text, target, options):
        #soup = BeautifulSoup(text, 'html.parser')
        soup = fragment_fromstring(text, create_parent=True)
        escape = html.escape

        # return HTML(text)
        console = context['.console']

        def write_error(insert_ref, el, msg, exc=None):
            log.error("insert '%s' failed; %s", insert_ref, msg)

            if context['.debug']:
                if exc is not None:
                    c = Console(text=True, width=120)
                    c.obj(context, exc)
                    _html = '<pre class="moya-insert-error"><code>{}</code></pre>'.format(escape(c.get_text()))
                else:
                    _html = '<pre class="moya-insert-error"><code>{}</code></pre>'.format(escape(msg))
                new_el = fromstring(_html)
                el.getparent().replace(el, new_el)
            else:
                el.getparent().remove(el)

            console.obj(context, exc)

        for el in self._selector(soup):

            try:
                insert_ref = el.attrib['insert']
            except IndexError:
                write_error(el, "no 'insert' attribute in <moya> markup tag")

            app = None
            app_name = el.attrib.get('app', None)
            if app_name is None:
                write_error(insert_ref, el, "'app' attribute is required on <moya> tag")
                continue

            # Get data params
            params = {k.split('-', 1)[-1]: v for k, v in el.attrib.items()
                      if k.startswith('data-')}
            params.update(options)

            app = app or context.get('.app', None)

            try:
                _app, insert_el = archive.get_element(insert_ref, app=app)
            except ElementNotFoundError as e:
                write_error(insert_ref, el, "markup insert element '{}' was not found".format(insert_ref), exc=e)
                continue

            if not getattr(insert_el, '_moya_markup_insert', False):
                msg = '{} is not safe for markup insertion'.format(html.escape(insert_el))
                write_error(insert_ref, el, msg)
                continue

            insert_callable = archive.get_callable_from_element(insert_el, app=_app)

            try:
                replace_markup = insert_callable(context, **params)
            except LogicError as e:
                write_error(insert_ref, el, "markup insert failed due to logic error, see logs", exc=e)
                continue
            except Exception as e:
                write_error(insert_ref, el, "markup insert failed, see logs", exc=e)
                continue

            new_el = fromstring(replace_markup)
            #new_el.head = el.head
            new_el.tail = el.tail
            el.getparent().replace(el, new_el)

        return HTML("".join(tostring(e).decode('utf-8') for e in soup.getchildren()))


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
