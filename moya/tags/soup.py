from __future__ import unicode_literals
from __future__ import print_function

from ..elements.elementbase import Attribute
from ..tags.context import DataSetter
from ..compat import text_type
from .. import namespaces

from lxml.cssselect import CSSSelector
from lxml.html import tostring, fromstring, fragment_fromstring

import json


class Strain(DataSetter):
    """
    Manipulate HTML with CSS selectors.

    The [c]select[/c] attribute should be a CSS selector which will filter tags from the [c]src[/c] string. The other attributes define what should happen to the matches tags.

    The following example defines a [tag]filter[/tag] which uses [tag]{soup}strain[/tag] to add [c]class="lead"[/c] to the first paragraph of HTML:

    [code xml]
    <filter name="leadp" value="html">
        <doc>Add class="lead" to first paragraph</doc>
        <soup:strain src="html" select="p" max="1" let:class="'lead'" dst="leadp"/>
        <return value="html:leadp"/>
    </filter>
    [/code]

    """
    xmlns = namespaces.soup

    class Help:
        synopsis = """modify HTML with CSS selectors"""

    select = Attribute("CSS selector", type="text", default="*")
    src = Attribute("HTML document or fragment", type="expression", required=True)

    append = Attribute("markup to append", type="expression", required=False, default=None)
    prepend = Attribute("markup to prepend", type="expression", required=False, default=None)
    replace = Attribute("markup to replace", type="expression", required=False, default=None)
    remove = Attribute("Remove matched element?", type="boolean", required=False)

    filter = Attribute("Filter by attributes", type="function", required=False, default=None)
    _max = Attribute("Maximum number of tags to match", type="integer", required=False, default=None)

    def logic(self, context):
        select, html = self.get_parameters(context, 'select', 'src')

        if not html.strip():
            self.set_context(context, self.dst(context), '')
            return

        let_map = self.get_let_map(context)

        if not html:
            self.set_context(context, self.dst(context), '')
            return
        try:
            selector = CSSSelector(select)
        except Exception as e:
            self.throw('soup.bad-selector', text_type(e))

        html_root = fragment_fromstring(html, create_parent=True)

        (append,
         replace,
         prepend,
         remove,
         _max) = self.get_parameters(context,
                                     'append',
                                     'replace',
                                     'prepend',
                                     'remove',
                                     'max')

        if self.has_parameter('filter'):
            filter_func = self.filter(context).get_scope_callable(context)
        else:
            filter_func = None

        count = 0
        for el in selector(html_root):
            if filter_func is not None:
                if not filter_func(el.attrib):
                    continue
            if _max is not None and count >= _max:
                break
            count += 1

            if let_map:
                attrib = el.attrib
                for k, v in let_map.items():
                    if v is None:
                        del attrib[k]
                    else:
                        attrib[k] = text_type(v)

            if append is not None:
                el.append(fragment_fromstring(append))
            if replace is not None:
                el.getparent().replace(el, fragment_fromstring(replace))
            if prepend is not None:
                el.insert(0, fragment_fromstring(prepend))
            if remove:
                el.getparent().remove(el)

        result_markup = "".join(tostring(child).decode('utf-8') for child in html_root.getchildren())
        self.set_context(context, self.dst(context), result_markup)


class Extract(DataSetter):
    """
    Extract tags from HTML with CSS selectors

    """
    xmlns = namespaces.soup

    class Help:
        synopsis = "extract tags from HTML"

    select = Attribute("CSS selector", type="text", default="*")
    src = Attribute("HTML document or fragment", type="expression", required=True)
    filter = Attribute("Filter by attributes", type="function", required=False, default=None)
    _max = Attribute("Maximum number of tags to match", type="integer", required=False, default=None)

    def logic(self, context):
        (select,
         html,
         filter,
         _max) = self.get_parameters(context,
                                     'select',
                                     'src',
                                     'filter',
                                     'max')

        if not html.strip():
            self.set_result(context, [])
            return

        try:
            selector = CSSSelector(select)
        except Exception as e:
            self.throw('soup.bad-selector', text_type(e))
        html_root = fromstring(html)

        if self.has_parameter('filter'):
            filter_func = self.filter(context).get_scope_callable(context)
        else:
            filter_func = None

        elements = []
        count = 0
        for el in selector(html_root):
            if filter_func is not None:
                if not filter_func(el.attrib):
                    continue
            if _max is not None and count >= _max:
                break
            count += 1
            elements.append(el)

        self.set_result(context, elements)

    def set_result(self, context, elements):
        result_markup = "".join(tostring(el).decode('utf-8') for el in elements)
        self.set_context(context, self.dst(context), result_markup)


class ExtractList(Extract):
    """
    Extract a list of markup fragments from HTML

    """
    xmlns = namespaces.soup

    class Help:
        synopsis = "extract a list of markup fragments from HTML"

    def set_result(self, context, elements):
        result = [tostring(el).decode('utf-8') for el in elements]
        self.set_context(context, self.dst(context), result)


class ExtractAttrs(Extract):
    """
    Extract attributes from HTML tags

    """
    xmlns = namespaces.soup

    class Help:
        synopsis = "extract attributes from HTML tags"

    def set_result(self, context, elements):
        result = [el.attrib for el in elements]
        self.set_context(context, self.dst(context), result)


class ExtractData(Extract):
    """
    Extract HTML5 data- attributes

    """
    xmlns = namespaces.soup

    raw = Attribute("return raw data (without attempting JSON decode)?", type="boolean", default=False)

    class Help:
        synopsis = "extract HTML5 data attributes from HTML"

    def set_result(self, context, elements):
        all_data = []
        raw = self.raw(context)

        def make_data(v):
            try:
                data = json.loads(v)
            except:
                data = v
            return data
        for el in elements:
            if raw:
                data = {k.partition('-')[-1]: v for k, v in el.attrib.items() if k.startswith('data-')}
            else:
                data = {k.partition('-')[-1]: make_data(v) for k, v in el.attrib.items() if k.startswith('data-')}

            all_data.append(data)
        self.set_context(context, self.dst(context), all_data)
