from ..docgen.doc import Doc
from ..elements import registry
from .. import bbcode
from .. import pilot
from .. import namespaces
from ..compat import text_type


from fs.path import join, splitext

from collections import defaultdict
from operator import itemgetter


class Extracter(object):
    """Extract documentation from code and external files"""
    def __init__(self, archive, fs):
        self.archive = archive
        self.fs = fs

    def _namespace_to_path(self, ns):
        if '://' in ns:
            ns = ns.split('://', 1)[-1]
        ns = ns.replace('/', '_').replace('.', '_dot_')
        return "xmlns/" + ns

    def _get_namespace_fs(self, ns):
        path = self._namespace_to_path(ns)
        namespace_fs = self.fs.makedirs(path)
        return namespace_fs

    def _get_lib_fs(self, libname):
        libname = libname.replace('.', '_')
        path = "libs/{libname}/docs".format(libname=libname)
        lib_fs = self.fs.makedirs(path)
        return lib_fs

    def slugify_namespace(self, ns):
        if ':' in ns:
            ns = ns.split(':', 1)[-1].lstrip('/')
        return ns.replace('/', '_').replace('.', '_dot_')

    def extract_docs(self, libname, docs_fs, const_data=None):
        docs = docs_fs.listdir(wildcard="*.txt")
        index = []
        docs_output_fs = self.fs.makedirs("docs/{}".format(libname))
        with pilot.console.progress("extracting {} docs".format(libname), len(docs)) as progress:
            for doc_name in progress(docs):
                default_name = splitext(doc_name)[0]
                code = docs_fs.gettext(doc_name)
                html, data = bbcode.parser.render(code)
                doc_name = data.get('name', default_name)
                data.update(body=code, name=doc_name, libname=libname, source=docs_fs.getsyspath(doc_name))
                doc = Doc('doc', doc_name, 'doc')
                doc.add_reference("index")
                doc.data.update(const_data or {})
                doc.data.update(data)
                data["id"] = doc.id
                doc.write(docs_output_fs)
                index.append(data)
            index.sort(key=lambda d: (d.get('section', ''), d["name"]))

    def extract_site_docs(self, docs_fs, const_data=None, dirname="docs"):
        docs = docs_fs.listdir(wildcard="*.txt")
        index = []
        docs_output_fs = self.fs.makedirs(dirname)
        with pilot.console.progress("extracting site docs", len(docs)) as progress:
            for doc_name in progress(docs):
                default_name = splitext(doc_name)[0]
                code = docs_fs.gettext(doc_name)
                html, data = bbcode.parser.render(code, path=docs_fs.getsyspath(doc_name))
                doc_name = data.get('name', default_name)
                data.update(body=code, name=doc_name)
                doc_class = data.get('class', 'doc')
                doc = Doc('doc', doc_name, doc_class)
                doc.add_reference("index")
                doc.data.update(const_data or {})
                doc.data.update(data)
                data["id"] = doc.id
                doc.write(docs_output_fs)
                index.append(data)
            index.sort(key=lambda d: (d.get('section', ''), d["name"]))

    def extract_namespace(self, ns, const_data=None):
        namespace_tags = registry.get_elements_in_xmlns(ns).items()
        self.extract_tags(namespace_tags, const_data=const_data)

    def extract_tags(self, elements, const_data=None):
        indices = defaultdict(list)
        tags = []
        tag_namespaces = set()
        with pilot.console.progress("extracting tags", len(elements) + 1) as progress:
            for element in progress(elements):
                tag_namespaces.add(element.xmlns)
                element_name = element._tag_name
                doc_namespace = "xmlns.{}".format(element.xmlns)
                if element._get_help('undocumented', False):
                    continue
                doc = Doc(doc_namespace, element_name, 'tag')
                doc.data.update(const_data or {})
                doc.data.update(element.extract_doc_info())
                doc.data.update(namespace=element.xmlns,
                                namespace_slug=self.slugify_namespace(element.xmlns),
                                name=element_name,
                                lib=element._lib_long_name)
                doc.data.update(const_data)
                doc.add_reference("doc.index")
                doc.add_reference('tags.index')
                indices[element.xmlns].append(doc.data)
                tags.append(doc.data)
                with self._get_namespace_fs(element.xmlns) as namespace_fs:
                    doc.write(namespace_fs)

            tags_index = Doc('tags', 'index', 'tags_index')
            tags_index.data.update(const_data or {})
            tags_index.data.update(namespaces=sorted(tag_namespaces))
            tags_index.data.update(tags=sorted(tags, key=lambda t: (t['tag_name'], t['namespace'])))
            tags_index.data['by_namespace'] = {}
            tags_index.data['namespaces'] = []
            for ns in tag_namespaces:
                tags_index.data['by_namespace'][ns] = []
                tags_index.data['namespaces'].append((ns, namespaces.namespace_docs.get(ns)))
            tags_index.data['namespaces'].sort()
            for tag in tags:
                tags_index.data['by_namespace'][tag['namespace']].append(tag)

            for index in tags_index.data['by_namespace'].values():
                index.sort(key=lambda t: (t['tag_name'], t['namespace']))
                for i, tag in enumerate(index):
                    try:
                        tag['next_tag'] = index[i + 1]['tag_name']
                    except IndexError:
                        pass
                    try:
                        tag['prev_tag'] = index[i - 1]['tag_name']
                    except IndexError:
                        pass

            tags_index.add_reference("doc.index")
            tags_index.write(self.fs)

            for ns in tag_namespaces:
                ns_slug = self.slugify_namespace(ns)
                ns_index = Doc("xmlns.{}".format(ns), '{}_index'.format(ns_slug), 'xmlns_index')
                ns_index.data.update(const_data or {})
                ns_index.data.update(tags=sorted(tags_index.data['by_namespace'][ns], key=lambda t: t['tag_name']),
                                     namespace=ns,
                                     namespace_doc=namespaces.namespace_docs.get(ns))
                ns_index.write(self.fs)

            progress.step()

    def extract_commands(self, elements, const_data=None):
        commands_output_fs = self.fs.makedir('commands')

        command_index = []
        with pilot.console.progress("extracting commands", len(elements) + 1) as progress:
            for element in progress(elements):
                doc = Doc('command', "command_{}".format(element.libname), 'command')
                doc.data.update(const_data or {})
                doc.data.update(element.extract_doc_info())
                doc.data.update(namespace=element.xmlns,
                                namespace_slug=self.slugify_namespace(element.xmlns),
                                name=element.libname,
                                doc=element._doc or '',
                                signature=element._signature,
                                synopsis=element._synopsis)
                command_index.append(doc.data)
                doc.write(commands_output_fs)

            command_index.sort(key=itemgetter('name'))
            doc = Doc('command_index', 'index', 'command_index')
            doc.data.update(const_data or {})
            doc.data['commands'] = command_index
            doc.write(commands_output_fs)

            progress.step()

    def extract_lib(self, long_name):
        lib = self.archive.libs[long_name]

        const_data = {
            "long_name": long_name,
            "lib": {
                "title": lib.title,
                "url": lib.url,
                "version": text_type(lib.version)
            },
            "author": lib.author
        }

        lib_cover = Doc('cover', 'cover', doc_class='cover')
        lib_cover.add_reference("doc.index")
        lib_cover.data.update(const_data)

        lib_cover.write(self.fs)

        if lib.documentation_location is not None:
            with lib.load_fs.opendir(lib.documentation_location) as docs_fs:
                self.extract_docs(long_name, docs_fs, const_data)

        lib_tags = self.archive.registry.get_elements_in_lib(long_name)
        self.extract_tags(lib_tags, const_data=const_data)
        commands = self.archive.get_elements_by_type(namespaces.default, 'command')
        self.extract_commands(commands, const_data=const_data)
