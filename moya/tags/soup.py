from __future__ import unicode_literals
from __future__ import print_function

from ..elements.elementbase import Attribute
from ..tags.context import DataSetter
from .. import namespaces

from lxml.cssselect import CSSSelector
from lxml.etree import tostring
from lxml.html import fromstring


class Strain(DataSetter):
    """
    Select html tags

    """
    xmlns = namespaces.soup

    class Help:
        synopsis = """select HTML tags"""

    select = Attribute("CSS selector", type="text", default="*")
    src = Attribute("HTML document or fragment", type="expression", required=True)

    append = Attribute("markup to append", type="expression", required=False, default=None)
    prepend = Attribute("markup to prepend", type="expression", required=False, default=None)
    replace = Attribute("markup to replace", type="expression", required=False, default=None)
    remove = Attribute("Remove matched element?", type="boolean", required=False)
    unwrap = Attribute("Remove outer tag", type="boolean", default=False, required=False)

    filter = Attribute("Filter by attributes", type="function", required=False, default=None)
    _max = Attribute("Maximum number of tags to match", type="integer", required=False, default=None)

    def logic(self, context):
        select, html = self.get_parameters(context, 'select', 'src')
        selector = CSSSelector(select)

        html_root = fromstring(html)

        (append,
         replace,
         prepend,
         remove,
         _max,
         unwrap) = self.get_parameters(context,
                                       'append',
                                       'replace',
                                       'prepend',
                                       'remove',
                                       'max',
                                       'unwrap')

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

            if append is not None:
                el.append(fromstring(append))
            if replace is not None:
                el.getparent().replace(el, fromstring(replace))
            if prepend is not None:
                el.insert(0, fromstring(prepend))
            if remove:
                el.getparent().remove(el)

        if unwrap:
            result_markup = "".join(tostring(child) for child in html_root.getchildren())
        else:
            result_markup = tostring(html_root)

        self.set_context(context, self.dst(context), result_markup)


class Extract(DataSetter):
    """
    Extract markup from HTML
    """
    xmlns = namespaces.soup

    class Help:
        synopsis = "extract markup from HTML"

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

        selector = CSSSelector(select)
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
        result_markup = "".join(tostring(el) for el in elements)
        self.set_context(context, self.dst(context), result_markup)


class ExtractList(Extract):
    """
    Extract a list of markup fragments from HTML

    """
    xmlns = namespaces.soup

    class Help:
        synopsis = "extract a list of markup fragments from HTML"

    def set_result(self, context, elements):
        result = [tostring(el) for el in elements]
        self.set_context(context, self.dst(context), result)
