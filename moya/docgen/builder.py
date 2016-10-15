from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from .. import pilot
from ..context import Context
from ..template.moyatemplates import MoyaTemplateEngine
from ..docgen.theme import Theme
from ..docgen.doc import Doc
from .. import bbcode
from .. import syntax
from ..filter import MoyaFilterBase

from fs import utils
from fs.opener import open_fs
from fs.path import *

from os.path import join as pathjoin
from json import loads
from collections import defaultdict


class _LocationFilter(MoyaFilterBase):

    def __moyafilter__(self, context, app, value, params):
        tag_index = params['index']
        next_tag = None
        prev_tag = None
        for i, tag in enumerate(tag_index):
            if tag['tag_name'] == value:
                try:
                    next_tag = tag_index[i + 1]
                except IndexError:
                    pass
                if i > 0:
                    try:
                        prev_tag = tag_index[i - 1]
                    except IndexError:
                        pass

        return (prev_tag, next_tag)


class Builder(object):
    """Generate html documentation"""

    def __init__(self, source_fs, output_fs, theme_fs):
        self.source_fs = source_fs
        self.output_fs = output_fs
        self.theme_fs = theme_fs
        self.template_engine = MoyaTemplateEngine(None, self.theme_fs, None)
        self.docs = {}
        self.theme = Theme(self.theme_fs)
        self.settings = None
        self.pages = {}
        self.doc_paths = {}
        self.indices = {}

    def build(self, build_data=None):

        source_fs = self.source_fs
        paths = list(source_fs.walkfiles(wildcard="*.json"))

        urls = defaultdict(dict)

        with pilot.console.progress("Reading", len(paths)) as progress:
            for path in progress(paths):
                doc_data = loads(self.source_fs.getcontents(path, 'rt'))
                doc = Doc.from_dict(doc_data)

                for page in self.theme.get_pages(doc):
                    data = doc.data
                    context = Context({"data": data})

                    with context.frame("data"):
                        path = page.get(context, 'path')
                        name = page.get(context, 'name')
                        full_path = self.output_fs.getsyspath(path)
                        if name:
                            urls[page.doc_class][name] = full_path
                        if 'namespace' in data:
                            urls[page.doc_class]["{{{}}}{}".format(data['namespace'], name)] = full_path

                self.docs[doc.id] = doc
                self.theme.get_pages(doc)

        self.process_indices(urls)

        assets_source_path = self.theme.get_relative_path(self.theme.get('assets', 'source', './assets'))
        assets_fs = open_fs(assets_source_path)

        with pilot.console.progress("Copying theme assets", None) as progress:
            def copy_progress(step, num_steps):
                progress.set_num_steps(num_steps)
                progress.update(step)
            utils.copydir_progress(copy_progress,
                                   assets_fs,
                                   (self.output_fs, 'assets'))

        with pilot.console.progress("Rendering", len(self.docs)) as progress:
            for doc in progress(self.docs.values()):
                self.render_doc(doc, urls, build_data)

        if 'doc' in urls:
            return urls['doc'].get('index', None)
        return None

    def process_indices(self, urls):
        for doc in self.docs.values():
            data = doc.data
            if 'indices' in data:
                doc_indices = data['indices']
                for index_name, (index_type, template, docs) in doc_indices.items():
                    if template:
                        index = docs
                    else:
                        index = []
                        for doc_name in docs:
                            doc_key = "doc.{}".format(doc_name)
                            indexed_doc = self.docs.get(doc_key, None)
                            if indexed_doc is None:
                                continue
                            index.append(indexed_doc)
                    self.indices[index_name] = (index_type, template, index)

    def render_index(self, context, index, template="docindex.html"):
        html = self.template_engine.render(template,
                                           {"index": index},
                                           base_context=context)
        return html

    _re_sub_index = re.compile(r'\{\{\{INDEX (.*?)\}\}\}')

    def sub_indices(self, context, html):
        def repl(match):
            index = self.indices.get(match.group(1), None)
            if index is not None:
                return self.render_index(context, index)
            return ''
        return self._re_sub_index.sub(repl, html)

    def get_doc(self, doc_id):
        return self.docs[doc_id]

    def get_navigation(self, doc_id):
        for index_type, template, index in self.indices.values():
            if template:
                continue
            for i, doc in enumerate(index):
                if doc.id == doc_id:
                    found = i
                    break
            else:
                continue
            nav = {}

            def seq(n):
                if index_type == 'A':
                    return chr(ord('A') + n - 1)
                elif index_type == 'a':
                    return chr(ord('a') + n - 1)
                else:
                    return n

            if found >= 1:
                nav['prev'] = {'index': seq(found), 'doc': index[found - 1]}
            if found < len(index) - 1:
                nav['next'] = {'index': seq(found + 2), 'doc': index[found + 1]}
            return nav
        return [None, None]

    def render_doc(self, doc, urls, render_data=None):

        for page in self.theme.get_pages(doc):
            data = doc.data
            context = Context({"data": data})

            #if 'docmap' in data:
            #    context['doctree'] = self.process_docmap(data['docmap'])
            context['bbcode'] = bbcode.parser
            context['syntax'] = syntax.SyntaxFilter()
            context['section'] = page.get(context, 'section')
            context['getnav'] = _LocationFilter()

            with context.frame("data"):
                output_path = page.get(context, 'path')
                output_dir = normpath(dirname(output_path))
                template = page.get(context, 'template')

            context['.doc'] = doc
            context['.path'] = output_path
            context['.root_path'] = self.output_fs.getsyspath('/')
            context['.request'] = {"path": self.output_fs.getsyspath(output_path)}  # Simulate a url request
            context['.urls'] = urls
            context['.nav'] = self.get_navigation(doc.id)
            context['.docs'] = self.docs

            if render_data is not None:
                context.root.update(render_data)

            assets = relpath(normpath(self.theme.get('assets', 'location', 'assets')))

            dir_level = output_dir.count('/') + 1 if output_dir else 0
            assets_path = pathjoin(dir_level * '../', assets) + '/'
            context['assets_path'] = assets_path
            with context.frame("data"):
                for doc_id in doc.references:
                    ref_doc = self.get_doc(doc_id)
                    context[ref_doc.name] = ref_doc.data
                #context['id'] = doc_id
            context['.id'] = doc.id

            html = self.template_engine.render(template, context['data'], base_context=context)
            html = self.sub_indices(context, html)

            self.output_fs.makedirs(output_dir, recreate=True)
            self.output_fs.setbytes(output_path, html)
