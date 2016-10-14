from __future__ import unicode_literals
from __future__ import print_function

from lxml import etree


import re
from collections import defaultdict
import io
import logging


from . import errors
from . import tags
from .tools import datetime_to_epoch
from .document import Document, DocumentStructure, DocumentNode, DocumentTextNode
from . import namespaces
from .containers import OrderedDict
from .cache.dictcache import DictCache
from .compat import text_type, string_types, binary_type

from fs.path import abspath
from fs.errors import NoSysPath

_re_xml_namespace = re.compile(r'^(?:\{(.*?)\})*(.*)$', re.UNICODE)


element_fromstring = etree.fromstring
log = logging.getLogger("moya.startup")


def extract_namespace(tag_name, _cache={}):
    """Extracts namespace and tag name in Clark's notation"""
    try:
        return _cache[tag_name]
    except KeyError:
        _cache[tag_name] = ns = _re_xml_namespace.match(tag_name).groups()
        return ns


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
        try:
            syspath = self.fs.getsyspath(path)
        except NoSysPath:
            syspath = None
        if syspath is None:
            self.location = self.fs.desc(path)
        else:
            self.location = syspath
        self._xml = None

    @property
    def xml(self):
        if self._xml is None:
            xml = self.fs.getbytes(self.path)
            xml = xml.replace(b'\t', b'    ')
            self._xml = xml
        return self._xml

    def parse(self, _extract_namespace=extract_namespace, _DocumentTextNode=DocumentTextNode, _DocumentNode=DocumentNode, _binary_type=binary_type):
        location = self.location
        document = Document(self.archive,
                            lib=self.library,
                            path=self.path)
        document.location = location
        default_namespace = namespaces.default


        # The parser cache is disable because it only speeds up startup by around 6%
        # Not quite ready to give up the idea and delete this code just yet - WM 11/11/2015

        # if self.cache.enabled:
        #     mtime = datetime_to_epoch(self.fs.getinfokeys(self.path, 'modified_time')['modified_time'])
        #     cache_key = "{}.{}".format(self.fs, self.path, mtime)
        #     cached_structure = self.cache.get(cache_key, None)
        #     if cached_structure is not None:
        #         document.structure = DocumentStructure.load(cached_structure, document, self.library)
        #         self.built = False
        #         return document

        xml = self.xml
        if xml.isspace() or not xml:
            log.warning("file '{}' is empty".format(self.location))
            return None

        structure = document.structure = DocumentStructure(document,
                                                           self.library,
                                                           xml)

        parser = etree.XMLParser()

        try:
            root = etree.parse(io.BytesIO(self.xml), parser).getroot()
        except Exception as e:
            error = getattr(e, 'msg', None) or text_type(e)
            raise errors.ParseError("XML failed to parse ({})".format(error),
                                    path=location,
                                    position=getattr(e, 'position', (1, 1)),
                                    code=xml)

        stack = [(root, None)]

        def make_unicode(s):
            if isinstance(s, _binary_type):
                return s.decode('utf-8')
            return s

        add_namespace = self.archive.known_namespaces.add
        while stack:
            node, parent_doc_id = stack.pop()
            if not isinstance(node.tag, string_types):
                continue
            xmlns, tag_name = _extract_namespace(make_unicode(node.tag))
            if xmlns is None:
                xmlns = default_namespace
            add_namespace(xmlns)

            translate_text = False
            if tag_name.startswith('_'):
                tag_name = tag_name[1:]
                translate_text = True

            attrs = defaultdict(OrderedDict)
            translatable_attrs = set()
            for k, v in node.items():
                attr_ns, attr_name = _extract_namespace(make_unicode(k))
                if attr_name.startswith('_'):
                    attr_name = attr_name[1:]
                    translatable_attrs.add(attr_name)
                attrs[attr_ns or default_namespace][attr_name] = make_unicode(v)

            source_line = getattr(node, "sourceline", None)
            doc_node = _DocumentNode(xmlns,
                                     tag_name,
                                     parent_doc_id,
                                     attrs,
                                     translatable_attrs,
                                     make_unicode(node.text),
                                     source_line,
                                     translate_text=translate_text)

            structure.add_node(doc_node)

            if node.tail:
                text_node = _DocumentTextNode(parent_doc_id,
                                              source_line,
                                              make_unicode(node.tail))
                structure.add_node(text_node)

            if node.text:
                doc_text_node = _DocumentTextNode(doc_node.doc_id,
                                                  doc_node.source_line,
                                                  make_unicode(node.text))
                structure.add_node(doc_text_node)

            stack.extend((child, doc_node.doc_id) for child in reversed(node))
        self.built = False

        # if self.cache.enabled:
        #     self.cache.set(cache_key, structure.dumps())

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
