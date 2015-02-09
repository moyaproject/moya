"""A container that contains information to generate documentation files"""
from __future__ import unicode_literals
from __future__ import print_function

from ..html import slugify
from ..compat import PY2

from json import dump


class Doc(object):
    def __init__(self, namespace, name, doc_class="document"):
        self.doc_namespace = namespace
        self.id = self.make_id(name)
        self.name = name
        self.doc_class = doc_class
        self.data = {}
        self.references = []

    def __repr__(self):
        return "<doc '{}'>".format(self.id)

    @classmethod
    def from_dict(cls, d):
        doc = cls(d['doc_namespace'],
                  d['name'],
                  d['doc_class'])
        doc.id = d['id']
        doc.data = d['data']
        doc.references = d['references']

        return doc

    def make_id(self, name):
        return "{}.{}".format(self.doc_namespace, name)

    def add_reference(self, name):
        doc_id = self.make_id(name) if '.' not in name else name
        self.references.append(doc_id)

    @property
    def package(self):
        data = {k: v for k, v in self.data.iteritems() if not k.startswith('_')}
        doc_package = {
            "id": self.id,
            "name": self.name,
            "doc_class": self.doc_class,
            "references": self.references,
            "data": data,
            "doc_namespace": self.doc_namespace
        }
        return doc_package

    def _process_docmap(self, docmap):
        doctree = [{"title": "Document",
                    "level": 0,
                    "children": []}]
        stack = [doctree[0]]

        for level, text in docmap:
            current_level = stack[-1]['level']
            node = {"title": text.strip(),
                    "slug": slugify(text),
                    "level": level,
                    "children": []}
            if level > current_level:
                stack[-1]['children'].append(node)
                stack.append(node)
            elif level == current_level:
                stack[-2]['children'].append(node)
                stack[-1] = node
            else:
                while level < stack[-1]['level']:
                    stack.pop()
                stack[-2]['children'].append(node)
                stack[-1] = node

        #def recurse(n, l=0):
        #    print("  " * l + n['title'])
        #    for child in n['children']:
        #        recurse(child, l + 1)
        #
        #recurse(doctree[0])

        doctree = doctree[0]['children']
        return doctree

    @property
    def doctree(self):
        if 'docmap' in self.data:
            doctree = self._process_docmap(self.data['docmap'])
        else:
            doctree = None
        return doctree

    def write(self, fs):
        """Write a pickle file containing the doc info"""
        doc_package = self.package
        filename = "{}.json".format(self.name).replace('/', '_')

        with fs.open(filename, 'wb' if PY2 else 'wt') as f:
            dump(doc_package, f, indent=4, separators=(',', ': '))
