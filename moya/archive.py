"""

docname = name in document
#libname = name in library
libname#docname = name in archive


"""
from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from . import elements
from .library import Library
from . import logic
from .tags.context import ContextElementBase
from .application import Application
from .document import Document
from . import errors
from .template import TemplateEngine
from .filesystems import FSWrapper, FSContainer
from .settings import SettingsContainer, SettingContainer, SettingsSectionContainer
from .console import Console
from .cache import Cache
from .mail import MailServer
from .sites import Sites
from .context import Context
from .filtercontainer import FilterContainer
from . import namespaces
from .containers import OrderedDict, LRUCache
from .elements.dataelement import DataElement
from .library import FailedDocument
from .elements.registry import ElementRegistry
from .tools import url_join
from .compat import text_type, iteritems, itervalues, zip_longest
from .tools import nearest_word
from .reader import DataReader
from .context.tools import to_expression
from . import logtools
from . import settings

from fs.opener import open_fs
from fs.multifs import MultiFS
from fs.mountfs import MountFS
from fs.path import join, abspath, relativefrom
from fs.errors import FSError

from collections import defaultdict, namedtuple, deque
import os
import io
import re
import sys
from time import time
import weakref
import logging
from operator import attrgetter


logging.raiseExceptions = False
log = logging.getLogger('moya.runtime')
startup_log = logging.getLogger('moya.startup')
signal_log = logging.getLogger('moya.signal')


FoundElement = namedtuple("Element", ["app", "element"])
TagData = namedtuple("TagData", ["app", "data"])


class Signals(object):
    """Manages signals"""

    def __init__(self):
        self._cache = LRUCache()
        self.handlers = []

    def add_handler(self, signal_name, element_ref, sender):
        self.handlers.append((signal_name, element_ref, sender))

    @classmethod
    def _compare_signal(cls, signal_name, compare_signal_name):
        """Compare signal names, potentially with a wildcard"""
        tokens = signal_name.split('.')
        compare_tokens = compare_signal_name.split('.')
        for compare, token in zip_longest(compare_tokens, tokens, fillvalue=None):
            if token == '*':
                return True
            if compare != token:
                return False
        return True

    def filter_handlers(self, signal, sender):
        """Return a list of handlers that match the given signal"""
        cache_key = (signal, sender)
        cache_result = self._cache.get(cache_key, None)
        if cache_result is not None:
            return cache_result

        handler_elements = []
        for signal_name, element_ref, handler_sender in self.handlers:
            if self._compare_signal(signal_name, signal):
                if handler_sender is None or sender == handler_sender:
                    handler_elements.append(element_ref)

        self._cache[cache_key] = handler_elements
        return handler_elements


class CallableElement(ContextElementBase):

    class Meta:
        tag_name = 'ExternalCall'
        is_call = True
        element_class = "logic"

    class Help:
        undocumented = True

    _element_type = ("http://moyaproject.com", "CallableElement")
    _location = __file__

    def __init__(self, archive, element, app=None, breakpoint=False):
        self.element = element
        self.app = app
        self.breakpoint = breakpoint
        self._document = weakref.ref(self.element.document)
        self.args = []
        self.kwargs = {}
        self.frame = None
        self._return_value = None
        self._code = None
        self._tag_name = "external-call '{}'".format(element.libid)
        self._attr_values = {}
        self._require_context = True
        self._debug_skip = True
        self.source_line = None
        self.libname = None
        self._docid = None

    def __repr__(self):
        return "<callable {}>".format(self.element.libid)

    def check(self, context):
        return True

    def logic(self, context):
        call = self.push_call(context, {'args': self.args} if self.args else {}, app=self.app)
        call.update(self.kwargs)
        if self.frame is None:
            try:
                for node in self.element.run(context):
                    yield node
            finally:
                call = self.pop_call(context)
        else:
            with context.data_frame(self.frame):
                try:
                    for node in self.element.run(context):
                        yield node
                finally:
                    call = self.pop_call(context)

        if self._return_value is None:
            self._return_value = call.get('_return')
        if hasattr(self._return_value, 'get_return_value'):
            self._return_value = self._return_value.get_return_value()

    def __call__(self, context, *args, **kwargs):
        return self.call(context, args, kwargs)

    def call(self, context, args, kwargs):
        self.args = args
        self.kwargs = kwargs
        if self.breakpoint and not self.archive.suppress_breakpoints:
            logic.debug(self.archive, context, self)
        else:
            logic.run_logic(self.archive, context, self)
        return self._return_value

    def call_frame(self, context, frame):
        self.frame = frame
        if self.breakpoint and not self.archive.suppress_breakpoints:
            logic.debug(self.archive, context, self)
        else:
            logic.run_logic(self.archive, context, self)
        return self._return_value


class SectionWrapper(object):
    """Wraps a settings section so that it produces a specific error for missing keys"""
    def __init__(self, section_name, section):
        self.section_name = section_name
        self.section = section

    def __getitem__(self, key):
        try:
            return self.section[key]
        except KeyError:
            error_text = "Required key [{section_name}]/{key} not found in settings".format(section_name=self.section_name,
                                                                                            key=key)
            raise errors.StartupFailedError(error_text)

    def __getattr__(self, key):
        return getattr(self.section, key)


class _BuildFrame(list):
    """An element and it's children"""
    def __init__(self, sequence, element=None):
        self.element = element
        super(_BuildFrame, self).__init__(sequence)


class Archive(object):

    _re_element_ref_match = re.compile(r'^(.+\..+)#(.*)$|^(.+)#(.*)$|^#(.+)$', re.UNICODE).match

    def __init__(self, project_fs=None, breakpoint=False, strict=False, test_build=False, develop=False):
        self.project_fs = project_fs
        self.strict = strict
        self.test_build = test_build
        self.develop = develop
        self.registry = ElementRegistry()
        self.libs = {}
        self.apps = OrderedDict()
        self.apps_by_lib = defaultdict(list)
        self.app_settings = defaultdict(SettingsContainer)
        self.app_system_settings = defaultdict(SettingsContainer)
        self.cfg = None
        self.settings = SettingsContainer()
        self.templates_fs = MultiFS()
        self.data_fs = MultiFS()
        self.filesystems = FSContainer({'templates': self.templates_fs,
                                        'data': self.data_fs})
        self.filters = FilterContainer(self)
        self.template_engines = {}
        self.database_engines = {}
        self.caches = {}
        self.mail_servers = {}
        self.default_mail_server = None
        self.default_db_engine = None
        self.debug = False
        self.struct = False
        self.auto_reload = False
        self.known_namespaces = set()
        self.sites = Sites()
        self.breakpoint = breakpoint
        self.suppress_breakpoints = False
        self.data_tags = defaultdict(list)
        self.data_tags_by_lib = defaultdict(lambda: defaultdict(list))  # awesome
        self.preflight = False
        self.log_signals = False
        self.debug_echo = False

        self.log_logger = None
        self.log_color = True
        self.log_width = None

        self.media_urls = None
        self.media_app = None

        self.failed_documents = []
        self.enum = {}
        self.enum_by_lib = {}
        self.signals = Signals()

        self._moyarc = None
        self.console = self.create_console()

    def __repr__(self):
        return "<archive>"

    @property
    def media_url(self):
        return self.media_urls[0] if self.media_urls else None

    @property
    def moyarc(self):
        if self._moyarc is None:
            try:
                with io.open(os.path.expanduser("~/.moyarc"), 'rt') as f:
                    self._moyarc = settings.SettingsContainer.read_from_file(f)
            except IOError:
                self._moyarc = settings.SettingsContainer()
        return self._moyarc

    def get_relative_path(self, path):
        """Get a relative path from the project base"""
        base = self.project_fs.getsyspath('/', allow_none=True)
        if base is None:
            return path
        return relativefrom(base, path)

    def open_fs(self, fs_url, create=False):
        if isinstance(fs_url, text_type):
            if '://' in fs_url:
                fs = open_fs(fs_url, create=create)
            else:
                if create:
                    self.project_fs.makedirs(fs_url, recreate=True)
                    fs = self.project_fs.opendir(fs_url)

                else:
                    fs = self.project_fs.opendir(fs_url)
        else:
            fs = fs_url
        return fs

    def get_console_file(self):
        if self.log_logger:
            console_file = logtools.LoggerFile(self.log_logger)
        else:
            console_file = None
        return console_file

    def create_console(self):
        console = Console(out=self.get_console_file(),
                          nocolors=not (self.log_color and self.moyarc.get_bool('console', 'color', True)),
                          width=self.log_width or None)
        return console

    def build_libs(self, ignore_errors=False):

        if self.test_build:
            ignore_errors = True

        libs = [lib for lib in itervalues(self.libs) if not lib.built]
        if not libs:
            return

        start = time()
        self.build([doc for lib in libs
                    for doc in lib.documents],
                   log_time=False)
        for lib in libs:
            lib.finalize(ignore_errors=ignore_errors)

        startup_log.debug("%s built libraries %0.1fms",
                          self,
                          (time() - start) * 1000.0)

    def build(self, documents, context=None, log_time=True, fs=None):
        """Build all documents in the library"""
        # This handles tags defined out of order
        if fs is not None:
            self.project_fs = fs
        start = time()

        if isinstance(documents, Document):
            documents = [documents]
        else:
            documents = list(documents)

        build_queue = deque()
        build_queue_appendleft = build_queue.appendleft

        for doc in documents:
            if not doc.document_finalized and doc.structure:
                build_queue.append(_BuildFrame([doc.structure.root_node]))

        unbuildable = set()
        unbuildable_clear = unbuildable.clear
        unbuilt = []

        if context is None:
            context = Context()

        context_root = context.root

        get_doc_id = attrgetter('doc_id')

        while build_queue:
            nodes = build_queue[0]
            if nodes:
                node = nodes.pop()
                context_root['_lib_long_name'] = node.lib_long_name
                element = node.build(self, context)
                if element:
                    unbuildable_clear()
                    build_queue_appendleft(_BuildFrame(sorted(node.children, key=get_doc_id, reverse=True), element=element))
                else:
                    if element is not None:
                        if node in unbuildable:
                            # A previously deferred node, but we still can't built it
                            build_queue.popleft()  # Can't process siblings either
                            unbuilt.append(node)
                        else:
                            # Defer this node till later
                            nodes.append(node)
                            build_queue.rotate(-1)
                            unbuildable.add(node)
            else:
                if nodes.element is not None:
                    unbuildable_clear()
                    try:
                        nodes.element.finalize(context)
                    except Exception as e:
                        raise
                        failed_doc = FailedDocument(path=node.structure.document.location,
                                                    code=node.structure.xml,
                                                    line=node.source_line,
                                                    col=None,
                                                    msg=text_type(e))
                        self.failed_documents.append(failed_doc)

                build_queue.popleft()

        if unbuilt:
            for node in unbuilt:
                nearest = nearest_word(node.tag_name,
                                       self.registry.get_elements_in_xmlns(node.xmlns))
                msg = "unknown tag {} in {}".format(node.tag_display_name, node.structure)
                diagnosis = None
                if nearest:
                    diagnosis = "did you mean <{}>?".format(nearest)
                else:
                    find_xmlns = self.registry.find_xmlns(node.tag_name)
                    if find_xmlns:
                        diagnosis = "did you mean <{}> in XMLNS '{}'?".format(node.tag_name, find_xmlns)
                failed_doc = FailedDocument(path=node.structure.document.location,
                                            code=node.structure.xml,
                                            line=node.source_line,
                                            col=None,
                                            msg=msg,
                                            diagnosis=diagnosis)
                self.failed_documents.append(failed_doc)
            return False

        if self.strict:
            failed = 0
            for doc in documents:
                failed += self.check_attributes(doc)
            if failed:
                startup_log.debug('%s %s strict check(s) failed', self, failed)
            else:
                startup_log.debug('%s strict checks passed', self)

        for doc in documents:
            doc.document_finalize(context)

        if log_time:
            doc_text = ', '.join(text_type(doc) for doc in documents)
            startup_log.debug("%s built %0.1fms",
                              doc_text,
                              (time() - start) * 1000.0)

        return True

    def check_attributes(self, doc):
        failed = 0
        for element_name, element in doc.elements.items():
            for k, attribute in element._tag_attributes.items():
                if k in element._attrs:
                    attr_text = element._attrs[k]
                    error = attribute.type.check(attr_text)
                    if error:
                        failed += 1
                        failed_doc = FailedDocument(path=doc.location,
                                                    code=element._code,
                                                    line=element.source_line or 0,
                                                    col=None,
                                                    msg="error in parameter '{}'; {}".format(k, error),
                                                    diagnosis="This check is performed when [project]/strict is enabled, or with 'moya runserver --strict' switch")
                        self.failed_documents.append(failed_doc)
        return failed

    def populate_context(self, context):
        from .context.expressiontime import ExpressionDateTime
        root = context.root
        root['libs'] = self.libs
        root['apps'] = self.apps
        root['filters'] = self.filters
        root['debug'] = self.debug
        root['develop'] = self.develop
        root['fs'] = self.get_context_filesystems()
        root['now'] = ExpressionDateTime.utcnow()
        from . import __version__
        root['moya'] = {'version': __version__}
        root['enum'] = self.enum
        root['media_url'] = self.media_url
        root['secret'] = self.secret
        context.set_dynamic('.app', lambda context: getattr(context.get('.call', None), 'app'))

    @classmethod
    def get_callable_from_document(cls, path, element_ref, breakpoint=False, fs='./', default_context=False, archive=None, lib=None):
        """Shortcut that imports a single document and returns a callable"""
        if archive is None:
            archive = cls()

        if lib is None:
            lib = archive.create_library(long_name="moya.run", namespace=namespaces.run)
            lib.import_document(fs, path)
        archive.build_libs()

        app, element = lib.documents[0].get_element(element_ref)
        if element is None:
            raise errors.ElementNotFoundError(element_ref, app=app)
        call = CallableElement(archive, element, app, breakpoint=breakpoint)
        if default_context:

            def do_call(*args, **kwargs):
                c = Context()
                c['console'] = Console()
                return call(c, *args, **kwargs)
            do_call.archive = archive
            return do_call

        return call

    @classmethod
    def parse_element_ref(cls, s, cache={}):
        try:
            return cache[s]
        except KeyError:
            match = cls._re_element_ref_match(s)
            if match is None:
                result = None, None, s
            else:
                libname, lib_elementname, appname, app_elementname, docname = match.groups()
                result = appname, libname, app_elementname or lib_elementname or docname
            cache[s] = result
            return result

    def get_library(self, library_name):
        """Get a library from either its short name, or its long name"""
        try:
            return self.libs[library_name]
        except KeyError:
            raise errors.UnknownLibraryError(lib=library_name)

    def has_library(self, library_name):
        return library_name in self.libs

    def load_library_from_module(self, py, **kwargs):
        __import__(py)
        module = sys.modules[py]
        location = os.path.dirname(os.path.abspath(module.__file__))
        import_fs = open_fs(location)
        lib = self.load_library(import_fs, **kwargs)
        return lib

    def load_library(self, import_fs, priority=None, template_priority=None, data_priority=None, long_name=None, rebuild=False):
        """Load a new library in to the archive"""
        lib = self.create_library(import_fs, long_name=long_name, rebuild=rebuild)
        if priority is not None:
            lib.priority = priority
        lib.data_priority = data_priority

        if lib.templates_info:
            fs_url = lib.templates_info['location']
            if template_priority is None:
                try:
                    template_priority = int(lib.templates_info.get('priority', '0'))
                except ValueError:
                    startup_log.error("{} invalid value for [templates]/priority, assuming 0".format(lib))
                    template_priority = 0
            lib.template_priority = template_priority
            if '://' in fs_url:
                fs = open_fs(fs_url)
            else:
                fs = import_fs.opendir(fs_url)
            self.templates_fs.add_fs(lib.long_name, fs, priority=template_priority)

        return lib

    def get_or_create_library(self, long_name, import_fs=None):
        """Get a library, or create it if it doesn't exists"""
        if long_name is not None and long_name in self.libs:
            return self.libs[long_name]
        return self.create_library(import_fs)

    def create_library(self, import_fs=None, long_name=None, namespace=None, rebuild=False):
        """Create a new library, and import documents"""
        lib = Library(self, import_fs, long_name=long_name, namespace=namespace, rebuild=rebuild)
        self.libs[lib.long_name] = lib
        return lib

    def finalize(self, ignore_errors=False):
        self.build_libs(ignore_errors=ignore_errors)

        for lib in itervalues(self.libs):
            lib.on_archive_finalize()

        if self.database_engines:
            for app in itervalues(self.apps):
                for model in app.lib.get_elements_by_type((namespaces.db, "model")):
                    if not model.abstract:
                        model.get_table_and_class(app)

    def create_app(self, name, lib_name):
        if name in self.apps:
            raise errors.ArchiveError("Application name '{}' was previously installed with {}".format(name, self.apps[name].lib))
        app = Application(self, name, lib_name)
        self.apps[name] = app
        app.settings.update(self.app_settings[name])
        app.system_settings.update(self.app_system_settings[name])
        self.apps_by_lib[lib_name].append(name)
        return app

    def get_app(self, app_id):
        try:
            return self.apps[app_id]
        except KeyError:
            return None

    def has_app(self, app_id):
        return app_id in self.apps

    def get_app_from_lib(self, lib, current=None):
        if isinstance(lib, Library):
            lib_name = lib.long_name
        else:
            lib_name = text_type(lib)
        if '.' not in lib_name:
            return lib_name
        apps = self.apps_by_lib[lib_name]
        if len(apps) != 1:
            if not apps:
                raise errors.AppRequiredError(lib_name)
            if current:
                if current.name in apps:
                    return current
            raise errors.AmbiguousAppError(lib_name, apps)
        return self.apps[apps[0]]

    def get_app_from_lib_default(self, lib, default=None):
        if isinstance(lib, Library):
            lib_name = lib.long_name
        else:
            lib_name = text_type(lib)
        if '.' not in lib_name:
            return lib_name
        apps = self.apps_by_lib[lib_name]
        if len(apps) != 1:
            return default
        return self.apps[apps[0]]

    def find_app(self, name):
        """
        Find an app from either its name or its lib name.

        If a lib name is supplied and there are more than one app, an AmbiguousAppError is raise

        """
        if isinstance(name, Application):
            return name
        if not name:
            raise errors.UnknownAppError("Value {} is not a valid app or lib name".format(to_expression(None, name)))
        name = text_type(name)
        try:
            if '.' in name:
                apps = self.apps_by_lib[name]
                if not apps:
                    raise KeyError("No app called '{}'".format(name))
                if len(apps) != 1:
                    raise errors.AmbiguousAppError(name, apps)
                return self.apps[apps[0]]
            else:
                return self.apps[name]
        except KeyError:
            raise errors.UnknownAppError(app=name)

    def find_app_default(self, name, default=None):
        try:
            return self.find_app(name)
        except errors.UnknownAppError:
            return default

    def get_app_settings(self, name):
        """
        Get settings object for an application.

        """
        app = self.find_app(name)
        return app.settings

    def detect_app(self, context, name):
        """
        Find an app from either its name or its libname

        if the app is ambiguous, attempt to detect it from the callstack.

        """
        if isinstance(name, Application):
            return name
        if not name:
            raise errors.UnknownAppError("Value {} is not a valid app or lib name".format(context.expr(name)))
        try:
            if '.' in name:
                apps = self.apps_by_lib[name]
                if not apps:
                    raise KeyError("No app called '{}'".format(name))
                if len(apps) != 1:
                    _app = context['.app']
                    if _app and _app.name in apps:
                        return _app
                    for c in reversed(context['._callstack']):
                        if c.app.name in apps:
                            return c.app
                    raise errors.AmbiguousAppError(name, apps)
                return self.apps[apps[0]]
            else:
                return self.apps[name]
        except KeyError:
            raise errors.UnknownAppError(app=name)

    def get_lib(self, name):
        if isinstance(name, Library):
            return name.long_name
        if '.' in name:
            return self.libs[name].long_name
        return self.find_app(name).lib.long_name

    def add_data_tag(self, element_type, tag):
        self.data_tags[element_type].append(tag)
        self.data_tags_by_lib[tag.lib.long_name][element_type].append(tag)

    def get_data(self, context, namespace, tag_name):
        """Get data from a data tag"""
        tag_type = (namespace, tag_name)

        return [e.get_all_data_parameters(context)
                for e in self.data_tags.get(tag_type, [])
                if e.check(context)]

    def get_data_item(self, context, namespace, tag_name, filter_map, lib=None):
        """Get data from a data tag"""
        tag_type = (namespace, tag_name)
        for e in self.data_tags.get(tag_type, []):
            if lib is not None:
                if e.lib != lib:
                    continue
            data = e.get_all_data_parameters(context)
            if all(filter_map[k] == data.get(k, Ellipsis)
                   for k, v in filter_map.items()):
                return data

    def get_data_from_element(self, context, element):
        return element.get_all_data_parameters(context)

    def get_data_elements(self, context, namespace, tag_name):
        """Get data from a data tag"""
        tag_type = (namespace, tag_name)
        return [DataElement(e, context)
                for e in self.data_tags.get(tag_type, [])
                if e.check(context)]

    def get_app_data_elements(self, context, namespace, tag_name):
        data = []
        tag_type = (namespace, tag_name)

        for app in itervalues(self.apps):
            _elements = []
            append = _elements.append
            for e in self.data_tags_by_lib[app.lib.long_name].get(tag_type, []):
                if e.check(context):
                    append(DataElement(e, context))
            if _elements:
                data.append((app, _elements))
        return data

    def add_filesystem(self, name, fs, create=False):
        try:
            add_fs = self.open_fs(fs, create=create)
        except FSError as e:
            raise errors.StartupFailedError("unable to open filesystem '{name}' ({e})".format(name=name, e=text_type(e)))
        self.filesystems[name] = add_fs
        #startup_log.debug("%s fs added as '%s'", add_fs, name)
        startup_log.debug("<%s '%s'> filesystem added", type(add_fs).__name__.lower(), name)
        return fs

    def get_filesystem(self, name):
        return self.filesystems[name]

    def has_filesystem(self, name):
        return name in self.filesystems

    def lookup_filesystem(self, element, name):
        try:
            return self.filesystems[name]
        except KeyError:
            raise element.throw("fs.no-filesystem",
                                "no filesystem called '{0}'".format(name),
                                diagnosis="You can view installed filesystems from the command line with **moya fs**")

    def get_reader(self, name="data"):
        fs = self.get_filesystem(name)
        return DataReader(fs)

    def get_context_filesystems(self):
        return FSContainer((k, FSWrapper(fs))
                           for k, fs in iteritems(self.filesystems))

    def get_translations(self, app_or_lib, languages):
        return self.find_app(app_or_lib).lib.translations.get(languages)

    def init_template_engine(self, system, settings):
        if system in self.template_engines:
            return
        engine = TemplateEngine.create(system,
                                       self,
                                       self.templates_fs,
                                       settings)
        self.template_engines[system] = engine
        startup_log.debug('%s template engine initialized', engine)

    def init_cache(self, name, settings):
        cache = Cache.create(name, settings)
        self.caches[name] = cache
        startup_log.debug('%s cache added', cache)

    def has_cache(self, name):
        """Check if a cache is present and enabled"""
        if name not in self.caches:
            return False
        cache = self.caches[name]
        return cache.enabled

    def get_cache(self, name):
        if name in self.caches:
            return self.caches[name]
        cache = self.caches[name] = Cache.create('runtime', SettingsSectionContainer({'type': 'dict'}))
        return cache

    def get_mailserver(self, name=None):
        name = name or self.default_mail_server or 'default'
        try:
            return self.mail_servers[name or 'default']
        except KeyError:
            raise errors.MoyaException("email.no-server", "no email server called '{0}'".format(name))

    def init_templates(self, name, location, priority):
        templates_fs = self.filesystems.get("templates")
        fs = self.open_fs(location)
        templates_fs.add_fs(name, fs, priority=priority)
        #startup_log.debug("added templates filesystem, priority %s", priority)

    def get_template_engine(self, engine="moya"):
        return self.template_engines[engine]

    def get_default_template_engine(self, app):
        engine = app.lib.templates_info.get('default_engine', 'moya')
        return engine

    def init_settings(self, cfg=None):
        cfg = cfg or self.cfg
        self.secret = cfg.get('project', 'secret', '')
        self.preflight = cfg.get_bool('project', 'preflight', False)
        self.debug = cfg.get_bool('project', 'debug')
        self.strict = self.strict or cfg.get_bool('project', 'strict')
        self.develop = self.develop or cfg.get_bool('project', 'develop')
        self.log_signals = cfg.get_bool('project', 'log_signals')
        self.debug_echo = cfg.get_bool('project', 'debug_echo')

        if 'console' in cfg:
            self.log_logger = cfg.get('console', 'logger', None)
            self.log_color = cfg.get_bool('console', 'color', True)
            self.log_width = cfg.get_int('console', 'width', None)
            self.console = self.create_console()

        self.sites.set_defaults(cfg['site'])

        if 'templates' not in self.caches:
            self.caches['templates'] = Cache.create('templates', SettingsSectionContainer({'type': 'dict'}))
        if 'runtime' not in self.caches:
            self.caches['runtime'] = Cache.create('runtime', SettingsSectionContainer({'type': 'dict'}))

        require_name = ['app', 'smtp', 'db']
        self.auto_reload = cfg.get_bool('autoreload', 'enabled')

        if self.strict:
            startup_log.debug('strict mode is enabled')
        if self.develop:
            startup_log.debug('develop mode is enabled')

        for section_name, section in iteritems(cfg):
            section = SectionWrapper(section_name, section)
            if ':' in section_name:
                what, name = section_name.split(':', 1)
            else:
                what = section_name
                name = None

            if what in require_name and not name:
                raise errors.StartupFailedError('name required in section, [{section}:?]'.format(section=what))

            if what in ('project', 'debug', 'autoreload', 'console', 'customize', ''):
                continue

            if what == "settings":
                if name is None:
                    self.settings.update((k, SettingContainer(v))
                                         for k, v in iteritems(section))
                else:
                    self.app_settings[name].update((k, SettingContainer(v))
                                                   for k, v in iteritems(section))
            elif what == 'application':
                self.app_system_settings[name].update(section)

            elif what == "lib":
                if self.has_library(name):
                    lib = self.get_library(name)
                    lib.settings.update((k, SettingContainer(v))
                                        for k, v in iteritems(section))

            elif what == "fs":
                location = section.get("location")
                if not location:
                    raise errors.StartupFailedError("a value for 'location' is required in [{}]".format(section_name))

                create = section.get_bool('create', False)
                self.add_filesystem(name, location, create=create)

            elif what == "data":
                location = section.get("location")
                data_fs = self.open_fs(location)
                self.data_fs.add_fs('archive',
                                    data_fs,
                                    priority=section.get_int('priority', 0))

            elif what == "cache":
                self.init_cache(name, section)

            elif what == "templates":
                location = section["location"]
                try:
                    priority = int(section["priority"])
                except (IndexError, ValueError):
                    priority = 0
                self.init_templates(name, location, priority)

            elif what == "db":
                from .db import add_engine
                add_engine(self, name, section)

            elif what == 'media':
                priority = section.get_int('priority', 1)
                location = section["location"]
                static_media_fs = self.open_fs(location)
                media_fs = MultiFS()
                media_fs.add_fs("static", static_media_fs, priority=priority)
                self.add_filesystem('media', media_fs)

                self.media_urls = section.get_list('url')
                self.media_app = section.get('app', 'media')

            elif what == "smtp":
                host = section["host"]
                port = section.get_int('port', 25)
                timeout = section.get_int('timeout', None)
                username = section.get('username', None)
                password = section.get("password", None)
                default = section.get_bool('default', False)
                sender = section.get('sender', None)
                server = MailServer(host,
                                    name=name,
                                    port=port,
                                    default=default,
                                    timeout=timeout,
                                    username=username,
                                    password=password,
                                    sender=sender)
                self.mail_servers[name] = server
                if self.default_mail_server is None or default:
                    self.default_mail_server = name
                if default:
                    startup_log.debug('%r (default) created', server)
                else:
                    startup_log.debug('%r created', server)

            elif what == "site":
                if name:
                    self.sites.add_from_section(name, section)

            elif what == "themes":
                location = section["location"]
                theme_fs = self.open_fs(location)
                self.add_filesystem('themes', theme_fs)
                #startup_log.debug("added theme filesystem '%s'", location)

            else:
                startup_log.warn("unknown settings section, [%s]", section_name)

        self.init_template_engine('moya', {})

    def init_media(self):
        if 'media' not in self.filesystems:
            return
        if not self.media_urls:
            if not self.media_app:
                raise errors.StartupFailedError("no 'url' or 'app' specified in [media] section")
            if self.media_app not in self.apps:
                startup_log.warning('app set in [media]/app has not been installed ({})'.format(self.media_app))
                return
            try:
                self.media_urls = [self.apps[self.media_app].mounts[0][1]]
            except:
                raise errors.StartupFailedError('unable to detect media url! (specify in [media]/url)')
        for i, _url in enumerate(self.media_urls):
            startup_log.debug('media url #%s is %s', i, _url)

        media_fs = self.filesystems['media']
        media_mount_fs = MountFS()
        for app in itervalues(self.apps):
            for media_name, media_sub_fs in iteritems(app.lib.media):
                name = "%s_%s" % (app.name, media_name)
                media_path = "%s-%s" % (app.name, media_name)
                app.media[media_name] = media_path
                if name in self.filesystems:
                    mount_media = self.filesystems[name]
                else:
                    mount_media = media_sub_fs
                if name not in self.filesystems:
                    self.filesystems[name] = mount_media
                media_mount_fs.mount(media_path, mount_media)
        media_fs.add_fs("media", media_mount_fs)

    def init_data(self):
        data_fs = self.data_fs
        for lib in itervalues(self.libs):
            data_priority = lib.data_info.get('priority', 0)
            if lib.data_priority is not None:
                data_priority = lib.data_priority
            if lib.data_fs is not None:
                data_fs.add_fs(lib.long_name, lib.data_fs, priority=data_priority)

    def get_media_url(self, context, app, media, path='', url_index=None):
        """Get a URL to media in a given app"""
        if url_index is None:
            url_index = context.inc('._media_url_index')
        if not self.media_urls:
            return None
        url_no = url_index % len(self.media_urls)
        if app is None:
            return url_join(self.media_urls[url_no] or '', path)
        return url_join(self.media_urls[url_no] or '',
                        app.get_media_directory(media),
                        path)

    @property
    def is_media_enabled(self):
        """Check if the media system is enabled"""
        return bool(self.media_urls)

    def get_element(self, element_ref, app=None, lib=None):
        """Gets an element from a reference"""
        app_id, lib_id, name = self.parse_element_ref(element_ref)
        if lib_id:
            lib = self.get_library(lib_id)
            element_app = self.get_app_from_lib_default(lib)
            element = lib.get_named_element(name)
        elif app_id:
            try:
                element_app = self.apps[app_id]
            except KeyError:
                raise errors.ElementNotFoundError(element_ref, app=app, lib=lib)
            element = element_app.lib.get_named_element(name)
        else:
            if app is not None:
                element_app = app
                element = app.lib.get_named_element(name)
            elif lib is not None:
                element_app = app
                element = lib.get_named_element(name)
            else:
                raise errors.ElementNotFoundError(element_ref, app=app, lib=lib)
        if element is None:
            raise errors.ElementNotFoundError(element_ref, app=app, lib=lib)
        return FoundElement(element_app, element)

    def get_app_element(self, element_ref):
        element_app = self.find_app(element_ref.split('#', 1)[0])
        app, element = self.get_element(element_ref, app=element_app)
        return app or element_app, element

    def resolve_template_path(self, path, app_name, base_path="/"):
        """Get a template path in the appropriate directory for an app"""
        if path.startswith('/'):
            return path
        if isinstance(app_name, Application):
            app = app_name
        else:
            app = self.find_app(text_type(app_name))
        app = app or self.detect_app()
        template_path = abspath(join(base_path, app.templates_directory, path))
        return template_path

    def get_template_lib(self, path, _cache=LRUCache()):
        if path in _cache:
            return _cache[path]
        lib = None
        for app in itervalues(self.apps):
            if path.startswith(app.templates_directory):
                lib = _cache[path] = app.lib.long_name
                break
        return lib

    def get_elements_by_type(self, ns, type):
        """Get all elements of a given namespace, type"""
        _elements = []
        extend = _elements.extend
        element_type = (ns, type)
        for lib in itervalues(self.libs):
            extend(lib.get_elements_by_type(element_type))
        return _elements

    def add_enum(self, libid, enum):
        """Add an enumeration"""
        self.enum[libid] = enum
        libname = libid.partition('#')[0]
        if enum.name:
            self.enum_by_lib.setdefault(libname, {})[enum.name] = enum

    def get_enum(self, enum_libid):
        """Get an enumeration"""
        return self.enum[enum_libid]

    def get_lib_enums(self, libname):
        """Get enumeration for a given lib"""
        return self.enum_by_lib.get(libname, None) or {}

    def fire(self, context, signal_name, app=None, sender=None, data=None):
        """Fire a signal"""
        if data is None:
            data = {}
        signal_obj = {
            "name": signal_name,
            "app": app,
            "sender": sender,
            "data": data
        }
        if self.log_signals:
            _params = context.to_expr(data)
            if sender:
                signal_log.debug('firing "%s" from "%s" %s', signal_name, sender, _params)
            else:
                signal_log.debug('firing "%s" %s', signal_name, _params)

        for element_ref in self.signals.filter_handlers(signal_name, sender):
            _, libname, _ = self.parse_element_ref(element_ref)
            for app_name in self.apps_by_lib[libname]:
                app = self.apps[app_name]
                try:
                    _callable = self.get_callable(element_ref, app=app)
                    _callable(context, signal=signal_obj)
                except errors.LogicError as e:
                    # We can't risk any unhdefandled exceptions here
                    try:
                        log.error("%s unhandled in signal '%s'", e, signal_name)
                    except:
                        pass
                    try:
                        if context['.debug']:
                            context['.console'].obj(context, e)
                    except:
                        pass

    def get_callable(self, element_ref, app=None, breakpoint=False):
        ref_app, element = self.get_element(element_ref, app=app)
        if element is None:
            raise errors.ElementNotFoundError(element_ref)
        return CallableElement(self, element, ref_app or app, breakpoint=breakpoint)

    def get_callable_from_element(self, element, app=None, breakpoint=False):
        return CallableElement(self, element, app, breakpoint=breakpoint)

    def call(self, element_ref, context, app, *args, **kwargs):
        _callable = self.get_callable(element_ref, app=app)
        return _callable(context, *args, **kwargs)

    def call_params(self, element_ref, context, app, params):
        _callable = self.get_callable(element_ref, app=app)
        return _callable(context, **params)

    def debug_call(self, element_ref, context, app, *args, **kwargs):
        _callable = self.get_callable(element_ref, app=app, breakpoint=True)
        return _callable(context, *args, **kwargs)

    __call__ = call


if __name__ == "__main__":
    archive = Archive()
    lib = archive.create_library()
    lib.import_documents("example")

    from moya.context import Context
    c = Context()

    mountpoint = archive.get_element('example#cmsmount')
    mountpoint.route("/article/2011/7/5/birthday/", c)
