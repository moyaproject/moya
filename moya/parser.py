from __future__ import unicode_literals

from lxml import etree
element_fromstring = etree.fromstring

import re
from collections import defaultdict
import io

from . import errors
from . import tags
from .document import Document, DocumentStructure, DocumentNode, DocumentTextNode
from . import namespaces
from .containers import OrderedDict
from .cache.dictcache import DictCache
from .compat import text_type, string_types

from fs.path import abspath

_re_xml_namespace = re.compile(r'^(?:\{(.*?)\})*(.*)$', re.UNICODE)


import logging
log = logging.getLogger("moya.startup")


def _extract_namespace(tag_name):
    """Extracts namespace and tag name in Clark's notation"""
    return _re_xml_namespace.match(tag_name).groups()


class Parser(object):

    _default_cache = DictCache('parser', '')

    def __init__(self, archive, fs, path, library=None):
        self.built = False
        try:
            self.cache = archive.get_cache('parser')
        except Exception as e:
            self.cache = self._default_cache
        self.archive = archive
        self.fs = fs
        self.path = abspath(path)
        self.library = library
        syspath = self.fs.getsyspath(path, allow_none=True)
        if syspath is None:
            self.location = self.fs.desc(path)
        else:
            self.location = syspath
        self._xml = None

    @property
    def xml(self):
        if self._xml is None:
            xml = self.fs.getcontents(self.path, 'rb')
            xml = xml.replace(b'\t', b'    ')
            self._xml = xml
        return self._xml

    def parse(self):
        location = self.location
        document = Document(self.archive,
                            lib=self.library,
                            path=self.path)
        document.location = location

        # if self.cache.enabled:
        #     mtime = datetime_to_epoch(self.fs.getinfokeys(self.path, 'modified_time')['modified_time'])
        #     cache_key = "{}.{}".format(self.fs, self.path, mtime)
        #     cached_structure = self.cache.get(cache_key, None)
        #     if cached_structure is not None:
        #         document.structure = DocumentStructure.load(cached_structure, document, self.library)
        #         self.built = False
        #         return document

        xml = self.xml
        if xml.isspace():
            return None

        structure = document.structure = DocumentStructure(document,
                                                           self.library,
                                                           xml)

        parser = etree.XMLParser()

        try:
            root = etree.parse(io.BytesIO(self.xml), parser).getroot()
        except Exception as e:
            raise errors.ParseError(text_type(e),
                                    path=location,
                                    position=getattr(e, 'position', (1, 1)),
                                    code=xml)

        document_encoding = "UTF-8"
        stack = [(root, None)]
        match_xml_namespace = _re_xml_namespace.match

        def make_unicode(s):
            if s is None:
                return s
            if not isinstance(s, text_type):
                return s.decode(document_encoding)
            return s

        while stack:
            node, parent_doc_id = stack.pop()
            if not isinstance(node.tag, string_types):
                continue
            xmlns, tag_name = match_xml_namespace(make_unicode(node.tag)).groups()
            if xmlns is None:
                xmlns = namespaces.default
            self.archive.known_namespaces.add(xmlns)

            translate_text = False
            if tag_name.startswith('_'):
                tag_name = tag_name[1:]
                translate_text = True

            attrs = defaultdict(OrderedDict)
            translatable_attrs = set()
            for k, v in node.items():
                k = make_unicode(k)
                v = make_unicode(v)
                attr_ns, attr_name = match_xml_namespace(k).groups()

                if attr_name.startswith('_'):
                    attr_name = attr_name[1:]
                    translatable_attrs.add(attr_name)
                attrs[attr_ns or namespaces.default][attr_name] = v

            source_line = getattr(node, "sourceline", None)
            doc_node = DocumentNode(xmlns,
                                    tag_name,
                                    parent_doc_id,
                                    attrs,
                                    translatable_attrs,
                                    make_unicode(node.text),
                                    source_line,
                                    translate_text=translate_text)

            structure.add_node(doc_node)

            if node.tail:
                text_node = DocumentTextNode(parent_doc_id,
                                             source_line,
                                             make_unicode(node.tail))
                structure.add_node(text_node)

            if node.text:
                doc_text_node = DocumentTextNode(doc_node.doc_id,
                                                 doc_node.source_line,
                                                 make_unicode(node.text))
                structure.add_node(doc_text_node)

            stack.extend((child, doc_node.doc_id) for child in reversed(node))
        self.built = False

        # if self.cache.enabled:
        #     self.cache.set(cache_key, structure.dumps())

        # log.debug("%s parsed %0.1fms",
        #           document,
        #           (time() - start) * 1000.0)

        return document


if __name__ == "__main__":

    test = """<logic xmlns="http://moyaproject.com">


<dict dst="fruit">
    <int dst="apples">3</int>
    <int dst="pears">7</int>
    <int dst="strawberries">10</int>
</dict>

<int dst="count" value="5" />
<while test="count">
    <debug>Count is ${count}</debug>
    <dec dst="count"/>
</while>
<eval dst="L">["apples", "oranges", "pears"]</eval>
<for src="L" dst="word">
    <for src="word" dst="c"><debug>${c}</debug></for>
    <debug>${word}</debug>
</for>

<dict dst="foo"/>
<str dst="foo.bar" value="Hello!"/>
<dict dst="foo" ifnot="foo" />
<debug>${foo.bar}</debug>
<frame context="foo">
    <str dst="bar" value="Bye!"/>
    <debug>${bar}</debug>
    <debug>${.foo.bar}</debug>
</frame>
<debug>${foo.bar}</debug>
</logic>

"""

    test = """<moya xmlns="http://moyaproject.com" xmlns:let="http://moyaproject.com/let">

<content libname="hello">
    <call let:foo="bar"/>
    <header>Hello</header>
    World
</content>

</moya>"""

    document_structure = Parser.parse_structure(test)
    document_structure.render()
