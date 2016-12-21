from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from .errors import ElementNotFoundError, ElementError
from .context.expression import Expression
from . import namespaces
from .compat import (text_type,
                     implements_to_string,
                     iteritems,
                     pickle)

from fs.path import dirname, join

import re
import weakref
from collections import defaultdict

_re_xml_namespace = re.compile(r'^(?:\{(.*?)\})*(.*)$', re.UNICODE)


def _extract_namespace(tag_name):
    """Extracts namespace and tag name in Clark's notation"""
    return _re_xml_namespace.match(tag_name).groups()


def _childless_tag(tag_name, attr_map):
    attrs = _get_attrs(attr_map)
    if attrs:
        a = ' '.join('%s="%s"' % (k, v) for k, v in sorted(attrs.items())).strip()
        return '<%s>' % ' '.join((tag_name, a))
    return '<%s>' % tag_name


def _get_attrs(attr_map):
    attrs = {}
    for ns, attr_map in attr_map.items():
        if ns == namespaces.default:
            ns = ''
        for k, v in iteritems(attr_map):
            if ns:
                attr_name = "{{{}}}{}".format(ns, k)
            else:
                attr_name = k
            attrs[attr_name] = v
    return attrs


@implements_to_string
class DocumentStructure(object):
    def __init__(self, document, library, xml):
        self.document = document
        self.library = library
        self.xml = xml
        self.doc_id = 1
        self.nodes = {}
        self.docid_counts = defaultdict(int)
        if library is not None:
            self.lib_long_name = library.long_name
        else:
            self.lib_long_name = None

    def __str__(self):
        return text_type(self.document)

    @property
    def top_nodes(self):
        root = self.nodes[1]
        return root.children

    @property
    def root_node(self):
        return self.nodes[1]

    def dumps(self):
        serialized = {
            "xml": self.xml,
            "nodes": self.nodes
        }
        return pickle.dumps(serialized, pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, doc_dump, document, library):
        serialized = pickle.loads(doc_dump)
        structure = DocumentStructure(document, library, serialized["xml"])
        nodes = serialized['nodes']
        for node in nodes.itervalues():
            node.structure = structure
        structure.nodes = nodes
        return structure

    @classmethod
    def quick_load(cls, document, library, xml, nodes):
        structure = DocumentStructure(document, library, xml)
        for node in nodes.itervalues():
            node.structure = structure
        structure.nodes = nodes
        return structure

    def add_node(self, node):
        doc_id = self.doc_id
        self.doc_id += 1
        self.nodes[doc_id] = node
        node.doc_id = doc_id
        if node.parent_doc_id is not None:
            self.nodes[node.parent_doc_id].children.append(node)
        node.structure = self
        node.lib_long_name = self.lib_long_name

    def render(self):
        def write_node(node, level=0):
            tab = "    " * level
            if isinstance(node, DocumentTextNode):
                print("{}{!r}".format(tab, node.text))
            else:
                print("{}{}".format(tab, node))
                for child in node.children:
                    write_node(child, level + 1)
        write_node(self.nodes[1])


@implements_to_string
class DocumentNode(object):
    def __init__(self,
                 xmlns,
                 tag_name,
                 parent_doc_id,
                 attrs,
                 translatable_attrs,
                 text,
                 source_line,
                 translate_text=False):
        self.text_node = False
        self.xmlns = xmlns
        self.tag_name = tag_name
        self.tag_type = (xmlns, tag_name)
        self.parent_doc_id = parent_doc_id
        self.attrs = attrs
        self.translatable_attrs = translatable_attrs
        self.source_line = source_line
        self.text = text
        self.translate_text = translate_text

        self.children = []
        self.structure = None
        self.text_nodes = None
        self.element = None
        self.lib_long_name = None

    def __repr__(self):
        return _childless_tag(self.xmlns_name, self.attrs)

    def __str__(self):
        return _childless_tag(self.xmlns_name, self.attrs)

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop('structure')
        return state

    @property
    def parent(self):
        if self.parent_doc_id:
            return self.structure.nodes[self.parent_doc_id]

    def build(self, archive, context):
        """Build an element from structure data"""
        # Returns element, or False if element could not be yet, or None if no element is required
        attrs = self.attrs.get(namespaces.default, {})
        docname = attrs.get('docname', None)
        libname = attrs.get('libname', None)
        structure = self.structure
        document = structure.document
        tag_name = self.tag_name

        structure.docid_counts[tag_name] += 1
        docid = "{}.{}".format(tag_name, structure.docid_counts[tag_name])

        if libname is None and structure.library is not None:
            libname = structure.library.allocate_libname(docid)

        replace_lib = False
        if libname is not None and '#' in libname:
            lib_, _, libname = libname.partition('#')
            lib = archive.get_or_create_library(lib_)
            replace_lib = True
        else:
            lib = self.structure.library

        element_type = archive.registry.get_element_type(self.xmlns, self.tag_name)
        if element_type is None:
            # We don't know how to build this yet
            # May be defined in a document not yet built
            return False

        if self.parent and self.parent.element:
            parent_docid = self.parent.element.docid
        else:
            parent_docid = None
        element = element_type(structure.document,
                               self.xmlns,
                               tag_name,
                               parent_docid,
                               docid,
                               source_line=self.source_line)
        element.libname = libname
        element.docname = docname
        element._code = structure.xml
        element._build(context, self.text or '', attrs, self.translatable_attrs)
        element._document = weakref.ref(document)

        element._let_exp = None  # Cache for let expressions
        element._let = self.attrs.get(namespaces.let, None)
        self.element = element

        element._translate_text = element._meta.translate or self.translate_text

        if element.parent:
            self.text_nodes = element._meta.text_nodes or element.parent._meta.text_nodes

        if docname is not None:
            document.register_named_element(docname, element)

        if lib:
            element._libid = "{}#{}".format(lib.long_name, libname)
            if replace_lib:
                lib.add_replacement_node(element)
            else:
                lib.register_named_element(libname,
                                           element,
                                           priority=structure.library.priority)

        return element

    @property
    def xmlns_name(self):
        if self.xmlns == namespaces.default:
            return self.tag_name
        else:
            return "{{{}}}{}".format(self.xmlns, self.tag_name)

    @property
    def tag_display_name(self):
        return "<{}>".format(self.xmlns_name)


class DocumentTextNode(DocumentNode):
    def __init__(self,
                 parent_doc_id,
                 source_line,
                 text):
        self.text_node = True
        self.parent_doc_id = parent_doc_id
        self.source_line = source_line
        self.text = text
        self.attrs = {}
        self.translatable_attrs = ()
        self.children = []
        self.translate_text = False

    def __repr__(self):
        return repr(self.text)

    def build(self, archive, context):
        text_nodes = self.parent.text_nodes
        if not text_nodes:
            return None
        xmlns, tag_name = _extract_namespace(self.parent.text_nodes)
        self.xmlns = xmlns or namespaces.default
        self.tag_name = tag_name
        self.tag_type = (self.xmlns, tag_name)
        element = super(DocumentTextNode, self).build(archive, context)
        if self.parent.translate_text:
            element.translate = True
        return element


class Document(object):

    def __init__(self, archive, lib=None, path=None):
        self._archive = weakref.ref(archive)
        self.elements = {}
        self.named_elements = {}
        self.root_element = None
        self.lib = lib
        self.fs = None
        self.path = path
        self.structure = None

        self.finalized = False
        self.document_finalized = False
        self.lib_finalized = False

    @property
    def archive(self):
        return self._archive()

    def __repr__(self):
        if self.lib:
            return "<document %s:\"%s\">" % (self.lib.long_name, self.path)
        else:
            return '<document "%s">' % self.path

    def __getitem__(self, element_id):
        return self.elements[element_id]

    def dumps(self, expressions=None):
        if expressions is None:
            expressions = []
        doc = {"expressions": expressions,
               "root": self.root_element.dumps()}
        return doc

    def loads(self, data):
        from .elements.elementbase import ElementBase
        Expression.insert_expressions(data["expressions"])
        self.root_element = ElementBase.loads(data["root"], self)
        return self

    def show(self):
        print()
        print(self)

        def recurse(node, level=0):
            print("{}{}".format(" " * (level * 4), node))
            for child in node._children:
                recurse(child, level + 1)
        if self.root_element:
            recurse(self.root_element)

    def get_element(self, element_ref, app=None, lib=None):
        try:
            if '#' not in element_ref:
                return app, self.named_elements[element_ref]
        except KeyError:
            raise ElementNotFoundError(element_ref, app=app, lib=lib)
        return self.archive.get_element(element_ref, app=app, lib=lib)

    def get_app_element(self, element_ref, app=None):
        if '#' in element_ref:
            app_id, lib_id, name = self.archive.parse_element_ref(element_ref)
            if lib_id is not None:
                try:
                    app = self.archive.find_app(lib_id)
                except Exception as e:
                    raise ElementNotFoundError(element_ref, app=app, reason=text_type(e))
                element_ref = "{}#{}".format(app.name, name)
        return self.get_element(element_ref, app=app)

    def detect_app_element(self, context, element_ref, app=None):
        if '#' in element_ref:
            app_id, lib_id, name = self.archive.parse_element_ref(element_ref)
            if lib_id is not None:
                try:
                    app = self.archive.detect_app(context, lib_id)
                except Exception as e:
                    raise ElementNotFoundError(element_ref, app=app, reason=text_type(e))
                element_ref = "{}#{}".format(app.name, name)
        return self.get_element(element_ref, app=app)

    def qualify_element_ref(self, element_ref, app=None, lib=None):
        if element_ref.find('#', 1) != -1:
            return element_ref
        app, element = self.get_element(element_ref, app=app, lib=lib)
        if element is None:
            raise ElementNotFoundError(element_ref, app=app, lib=lib)
        if self.lib:
            if app is not None:
                qname = app.name
            else:
                qname = self.lib.long_name
            return "%s#%s" % (qname, element.libname)
        return element_ref

    qualify = qualify_element_ref

    def get_root(self):
        return self.root_element
    root = property(get_root)

    def register_element(self, element):
        self.elements[element.docid] = element
        if element.parent_docid is not None:
            self.elements[element.parent_docid]._add_child(element)
        else:
            self.root_element = element

    def register_named_element(self, docname, element):
        if docname in self.named_elements:
            raise ElementError("docname '{}' is already present in this document".format(docname),
                               element=element)
        self.named_elements[docname] = element

    def get_named_element(self, docname):
        return self.named_elements.get(docname, None)

    def iter_elements(self):
        return self.elements.iter_values()

    def __iter__(self):
        return self.iter_elements()

    def resolve_relative_path(self, path):
        document_dirname = dirname(self.path)
        new_path = join(document_dirname, path)
        return new_path

    def finalize(self, context):
        if self.finalized:
            return
        ignore_errors = bool(context['._ignore_finalize_errors'])

        def do_finalize(element):
            for child in element:
                do_finalize(child)
            try:
                element.finalize(context)
            except:
                if not ignore_errors:
                    raise
        if self.root:
            do_finalize(self.root)
        self.finalize = True

    def document_finalize(self, context):
        if self.document_finalized:
            return
        ignore_errors = bool(context['._ignore_finalize_errors'])

        def do_finalize(element):
            for child in element:
                do_finalize(child)
            try:
                element.document_finalize(context)
            except:
                if not ignore_errors:
                    raise
        if self.root:
            do_finalize(self.root)
        self.document_finalized = True

    def lib_finalize(self, context):
        if self.lib_finalized:
            return
        ignore_errors = bool(context['._ignore_finalize_errors'])

        def do_finalize(element):
            for child in element._children:
                do_finalize(child)
            try:
                element.lib_finalize(context)
            except:
                if not ignore_errors:
                    raise
        if self.root_element:
            do_finalize(self.root_element)
        self.lib_finalized = True
