from __future__ import unicode_literals
from __future__ import absolute_import

from .. import namespaces
from ..elements import Attribute
from ..elements.elementbase import LogicElement
from ..tags.context import DataSetter

from fs.errors import FSError
from fs.path import pathjoin, basename, dirname

import hashlib


class SetContents(LogicElement):
    """Set the contents of a file"""
    xmlns = namespaces.fs

    class Help:
        synopsis = "write data to a file"

    fsobj = Attribute("Filesystem object", required=False, default=None)
    fs = Attribute("Filesystem name", required=False, default=None)
    path = Attribute("Destination path", required=True)
    contents = Attribute("File contents", type="expression", required=True)

    def logic(self, context):
        params = self.get_parameters(context)
        if self.has_parameter('fsobj'):
            dst_fs = params.fsobj
        else:
            dst_fs = self.archive.get_filesystem(params.fs)
        dst_fs.makedir(dirname(params.path), recursive=True, allow_recreate=True)
        dst_fs.setcontents(params.path, params.contents)


class GetMD5(DataSetter):
    """Get the MD5 of a file"""
    xmlns = namespaces.fs

    class Help:
        synopsis = "get the md5 of a file"

    fsobj = Attribute("Filesystem object", required=False, default=None)
    fs = Attribute("Filesystem name", required=False, default=None)
    path = Attribute("Path of file", required=True)

    def get_value(self, context):
        params = self.get_parameters(context)
        if self.has_parameter('fsobj'):
            fs = params.fsobj
        else:
            fs = self.archive.get_filesystem(params.fs)

        m = hashlib.md5()
        try:
            with fs.open(params.path, 'rb') as f:
                while 1:
                    chunk = f.read(16384)
                    if not chunk:
                        break
                    m.update(chunk)
        except FSError:
            self.throw("get-md5.fail", "unable to read file '{}'".format(params.path))
        else:
            return m.hexdigest()


class Walk(DataSetter):
    """Get a list of files"""
    xmlns = namespaces.fs

    class Help:
        synopsis = "go through the files in a directory"

    fsobj = Attribute("Filesystem object", required=False, default=None)
    path = Attribute("Path to walk", required=False, default="/")
    fs = Attribute("Filesystem name", required=False, default=None)
    dirs = Attribute("Filter directories (function should reference 'name' and return a boolean)", type="function", default=None)
    files = Attribute("Filter files (function should reference 'name' and return a boolean)", type="function", default=None)
    search = Attribute("Search method", default="breadth", choices=["breadth", "depth"])
    dst = Attribute("Destination", required=True, type="reference")

    def logic(self, context):
        params = self.get_parameters(context)
        if self.has_parameter('fsobj'):
            walk_fs = params.fsobj
        else:
            walk_fs = self.archive.get_filesystem(params.fs)

        wildcard = lambda name: params.files(context, name=basename(name)) if self.has_parameter('files') else lambda name: True
        dir_wildcard = lambda name: params.dirs(context, name=basename(name)) if self.has_parameter('dirs') else lambda name: True

        paths = []
        add_path = paths.append

        for dirname, dir_paths in walk_fs.walk(path=params.path,
                                               search=params.search,
                                               wildcard=wildcard,
                                               dir_wildcard=dir_wildcard,
                                               ignore_errors=True):

            for path in dir_paths:
                add_path(pathjoin(dirname, path))
        self.set_context(context, params.dst, paths)
