from __future__ import unicode_literals
import sys
import imp
import marshal

from .tags.service import ServiceCallElement
from .document import Document
from .elements.registry import ElementRegistry
from .compat import iteritems

from fs.path import combine, abspath
from fs.errors import NoSysPath
from fs.walk import walk_files

from . import expose
from . import errors


class LibraryImportHook(object):

    _VALID_MODULE_TYPES = set((imp.PY_SOURCE, imp.PY_COMPILED))

    def __init__(self, fs):
        self.fs = fs
        self.module_info = {}
        self._files = set(walk_files(fs))

    def install(self):
        if self not in sys.meta_path:
            sys.meta_path.append(self)

    def uninstall(self):
        try:
            sys.meta_path.remove(self)
        except ValueError:
            pass

    def _get_path(self, fullname):
        if fullname == "__moyapy__":
            return '/'
        _, path = fullname.split('.', 1)
        path = abspath(path.replace('.', '/'))
        return path

    def _get_module_info(self, fullname):
        if not fullname.startswith('__moyapy__'):
            raise ImportError(fullname)

        path = self._get_path(fullname)

        module_path, _type = self._find_module_file(path)
        if module_path is not None:
            return module_path, _type, False

        module_path, _type = self._find_module_file(combine(path, '__init__'))
        if module_path is not None:
            return module_path, _type, True

        raise ImportError(fullname)

    def get_module_info(self, fullname):
        if fullname in self.module_info:
            return self.module_info[fullname]
        module_info = self._get_module_info(fullname)
        self.module_info[fullname] = module_info
        return module_info

    def _find_module_file(self, path):
        for (suffix, mode, type) in imp.get_suffixes():
            if type in self._VALID_MODULE_TYPES:
                check_path = path + suffix
                #if self.fs.isfile(check_path):
                if check_path in self._files:
                    return (check_path, type)
        return (None, None)

    def find_module(self, fullname, path=None):
        try:
            self.get_module_info(fullname)
        except ImportError:
            return None
        else:
            return self

    def is_package(self, fullname, info=None):
        """Check whether the specified module is a package."""
        if info is None:
            info = self.get_module_info(fullname)
        (path, type, ispkg) = info
        return ispkg

    def get_filename(self, fullname, info=None):
        """Get the __file__ attribute for the specified module."""
        if info is None:
            info = self.get_module_info(fullname)
        (path, type, ispkg) = info
        if self.fs.hassyspath(path):
            path = self.fs.getsyspath(path)
        return path

    def load_module(self, fullname):
        """Load the specified module.

        This method locates the file for the specified module, loads and
        executes it and returns the created module object.
        """
        #  Reuse an existing module if present.
        #try:
        #    return sys.modules[fullname]
        #except KeyError:
        #    pass
        #  Try to create from source or bytecode.
        info = self.get_module_info(fullname)
        code = self.get_code(fullname, info)
        if code is None:
            raise ImportError(fullname)
        mod = imp.new_module(fullname)
        mod.__file__ = self.get_filename(fullname, info)
        mod.__loader__ = self
        sys.modules[fullname] = mod
        try:
            exec(code, mod.__dict__)
            if self.is_package(fullname, info):
                mod.__path__ = []

            return mod
        except Exception:
            sys.modules.pop(fullname, None)
            raise

    def get_code(self, fullname, info=None):
        """Get the bytecode for the specified module."""
        if info is None:
            info = self._get_module_info(fullname)
        path, type, ispkg = info
        code = self.fs.getbytes(path)
        if type == imp.PY_SOURCE:
            code = b'\n'.join(code.splitlines())
            try:
                path = self.fs.getsyspath(path)
            except NoSysPath:
                pass
            return compile(code, path, "exec")
        elif type == imp.PY_COMPILED:
            if code[:4] != imp.get_magic():
                return None
            return marshal.loads(code[8:])
        return code


def fs_import(lib, fs, name):
    hook = LibraryImportHook(fs)
    try:
        ElementRegistry.push_registry(lib.archive.registry)
        hook.install()

        expose.exposed_elements.clear()
        expose.exposed_filters.clear()

        module_name = "__moyapy__." + name
        if module_name in sys.modules:
            del sys.modules[module_name]
            #reload(sys.modules[module_name])

        try:
            module = __import__(module_name)
        except ImportError as e:
            raise errors.StartupFailedError("import error raised for Python extension '{}' ({})".format(name, e))

        add_module = getattr(module, name)
        lib.py[name] = add_module

        for element_name, element_callable in iteritems(expose.exposed_elements):
            document = Document(lib.archive, lib=lib)
            element = ServiceCallElement(lib.archive, element_name, element_callable, document)
            lib.documents.append(document)
            lib.register_element(element)
            lib.register_named_element(element_name, element)

        lib.filters.update(expose.exposed_filters)

        expose.exposed_elements.clear()
        expose.exposed_filters.clear()

    finally:
        ElementRegistry.pop_registry()
        hook.uninstall()


if __name__ == "__main__":
    from fs.opener import open_fs
    m = open_fs("mem://")
    m.createfile('__init__.py')
    m.makedir("test")
    m.setbytes(b'test/__init__.py', 'print "Imported!"\ndef run():print "It Works!"')
    m.tree()

    hook = LibraryImportHook(m)
    hook.install()

    module = __import__("__moyapy__.test")
    #print module.test.run
    module.test.run()

    #print imp.find_module("moyapy.test")
