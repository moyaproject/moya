from __future__ import unicode_literals
from __future__ import absolute_import

from .. import namespaces
from ..elements import Attribute
from ..elements.elementbase import LogicElement
from ..tags.context import DataSetter
from ..compat import text_type

from fs.errors import FSError
from fs.path import dirname
import fs.walk
from fs import wildcard

import hashlib
import logging

log = logging.getLogger('moya.fs')


class SetContents(LogicElement):
    """Set the contents of a file"""
    xmlns = namespaces.fs

    class Help:
        synopsis = "write data to a file"

    fsobj = Attribute("Filesystem object", required=False, default=None)
    fs = Attribute("Filesystem name", required=False, default=None)
    path = Attribute("Destination path", required=True)
    contents = Attribute("File contents", type="expression", required=True, missing=False)

    def logic(self, context):
        params = self.get_parameters(context)
        params.contents
        if self.has_parameter('fsobj'):
            dst_fs = params.fsobj
        else:
            dst_fs = self.archive.lookup_filesystem(self, params.fs)
        try:
            dst_fs.makedirs(dirname(params.path), recreate=True)
            if hasattr(params.contents, 'read'):
                dst_fs.setfile(params.path, params.contents)
            elif isinstance(params.contents, bytes):
                dst_fs.setfile(params.path, params.contents)
            elif isinstance(params.contents, text_type):
                dst_fs.settext(params.path, params.contents)
        except Exception as e:
            self.throw("fs.set-contents.fail", "unable to set file contents ({})".format(e))
        log.debug("setcontents '%s'", params.path)


class RemoveFile(LogicElement):
    """Delete a file from a filesystem"""
    xmlns = namespaces.fs

    class Help:
        synopsis = "delete a file"

    fsobj = Attribute("Filesystem object", required=False, default=None)
    fs = Attribute("Filesystem name", required=False, default=None)
    path = Attribute("Destination path", required=True)
    ifexists = Attribute("Only remove if the file exists?", type="boolean", required=False)

    def logic(self, context):
        params = self.get_parameters(context)
        if self.has_parameter('fsobj'):
            dst_fs = params.fsobj
        else:
            dst_fs = self.archive.lookup_filesystem(self, params.fs)
        if params.ifexists and dst_fs.isfile(params.path):
            return
        try:
            dst_fs.remove(params.path)
        except Exception as e:
            self.throw("fs.remove-file.fail",
                       "unable to remove '{}' ({})".format(params.path, e))
        log.debug("removed '%s'", params.path)


class GetSyspath(DataSetter):
    """
    Get a system path for a path in a filesystem.

    A system path (or 'syspath') is a path that maps to the file on the
    OS filesystem. Not all filesystems can generate syspaths. If Moya is
    unable to generate a syspath it will throw a [c]get-syspath.no-
    syspath[/c] exception.

    """
    xmlns = namespaces.fs

    class Help:
        synopsis = "get a system path"
        example = """
        <fs:get-syspath fs="templates" path="index.html" dst="index_template_path"/>
        """

    fsobj = Attribute("Filesystem object", required=False, default=None)
    fs = Attribute("Filesystem name", required=False, default=None)
    path = Attribute("Destination path", required=True)

    def logic(self, context):
        params = self.get_parameters(context)

        if self.has_parameter('fsobj'):
            dst_fs = params.fsobj
        else:
            dst_fs = self.archive.lookup_filesystem(self, params.fs)

        try:
            syspath = dst_fs.getsyspath(params.path)
        except:
            self.throw('fs.get-syspath.no-syspath',
                       "{!r} can not generate a syspath for '{}'".format(dst_fs, params.path))
        self.set_context(context, self.dst(context), syspath)


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
            fs = self.archive.lookup_filesystem(self, params.fs)

        m = hashlib.md5()
        try:
            with fs.open(params.path, 'rb') as f:
                while 1:
                    chunk = f.read(16384)
                    if not chunk:
                        break
                    m.update(chunk)
        except FSError:
            self.throw("fs.get-md5.fail", "unable to read file '{}'".format(params.path))
        else:
            return m.hexdigest()


class GetInfo(DataSetter):
    xmlns = namespaces.fs

    class Help:
        synopsis = "get an info object for a file"

    fsobj = Attribute("Filesystem object", required=False, default=None)
    fs = Attribute("Filesystem name", required=False, default=None)
    path = Attribute("Path of file", type="expression", required=True)

    def get_value(self, context):
        params = self.get_parameters(context)
        if self.has_parameter('fsobj'):
            fs = params.fsobj
        else:
            fs = self.archive.lookup_filesystem(self, params.fs)

        try:
            info = fs.getinfo(params.path)
        except FSError:
            self.throw('fs.get-info.fail', "unable to get info for path '{}'".format(params.path))
        else:
            return info


class GetSize(DataSetter):
    xmlns = namespaces.fs

    class Help:
        synopsis = "get the size of a file"

    fsobj = Attribute("Filesystem object", required=False, default=None)
    fs = Attribute("Filesystem name", required=False, default=None)
    path = Attribute("Path of file", type="expression", required=True)

    def get_value(self, context):
        params = self.get_parameters(context)
        path = text_type(params.path)
        if self.has_parameter('fsobj'):
            fs = params.fsobj
        else:
            fs = self.archive.lookup_filesystem(self, params.fs)

        try:
            info = fs.getsize(path)
        except FSError:
            self.throw('fs.get-size.fail', "unable to get info for path '{}'".format(params.path))
        else:
            return info


class MoyaWalker(fs.walk.Walker):

    def __init__(self, exclude_dirs):
        self.exclude_dirs = exclude_dirs

    def check_open_dir(self, fs, info):
        return not self.exclude_dirs(info.name)


class WalkFiles(DataSetter):
    """Recursively get a list of files in a filesystem."""
    xmlns = namespaces.fs

    class Help:
        synopsis = "recursively list files in a directory"

    fsobj = Attribute("Filesystem object", required=False, default=None)
    path = Attribute("Path to walk", required=False, default="/")
    fs = Attribute("Filesystem name", required=False, default=None)
    files = Attribute('One or more wildcards to filter results by, e.g "*.py, *.js"', type="commalist", default='*')
    excludedirs = Attribute('Directory wildcards to exclude form walk, e.g. "*.git, *.svn"', type="commalist", default=None)
    search = Attribute("Search method ('breadth' or 'depth')" , default="breadth", choices=["breadth", "depth"])
    dst = Attribute("Destination", required=True, type="reference")

    def logic(self, context):
        params = self.get_parameters(context)
        if self.has_parameter('fsobj'):
            walk_fs = params.fsobj
        else:
            walk_fs = self.archive.get_filesystem(params.fs)
        if params.excludedirs:
            walker = MoyaWalker(
                wildcard.get_matcher(params.excludedirs, True)
            )
        else:
            walker = fs.walk.Walker()
        paths = list(
            walker.walk_files(
                walk_fs,
                params.path,
                search=params.search,
                wildcards=params.files or None
            )
        )
        self.set_context(context, params.dst, paths)
