"""
A proxy for a webob request

"""

from __future__ import unicode_literals
from __future__ import print_function

from .interface import AttributeExposer
from .compat import implements_to_string
from .console import Cell

from webob import Request

import weakref
import os
from cgi import FieldStorage


@implements_to_string
class _MultiProxy(object):
    def __init__(self, multidict, name):
        self._multidict = weakref.ref(multidict)
        self.name = name

    def __moyaconsole__(self, console):
        from .console import Cell
        table = [(Cell("Name", bold=True), Cell("Value", bold=True))]
        table += sorted((k, self.getall(k)) for k in set(self.iterkeys()))
        console.table(table)

    @property
    def multidict(self):
        return self._multidict()

    def __str__(self):
        return "<multidict {}>".format(self.name)

    def __repr__(self):
        return repr(self.multidict)

    def __getitem__(self, key):
        if key not in self.multidict:
            raise KeyError("Key '{}' not in multi dict".format(key))
        return self.multidict.getall(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __getattr__(self, name):
        return getattr(self.multidict, name)


class UploadFileProxy(AttributeExposer):

    __moya_exposed_attributes__ = ['filename', 'size']

    def __init__(self, field_storage):
        self.field_storage = field_storage
        file = self.file = field_storage.file
        self.read = file.read
        self.seek = file.seek
        self.tell = file.tell
        self.readline = file.readline
        self.filename = field_storage.filename

    def __moyafile__(self):
        return self.file

    def __repr__(self):
        return '<upload "{}">'.format(self.filename)

    @property
    def size(self):
        if hasattr(self.file, 'fileno'):
            size = os.fstat(self.file.fileno()).st_size
        else:
            pos = self.tell()
            size = None
            try:
                self.seek(0, os.SEEK_END)
                size = self.tell()
            finally:
                self.seek(pos)
        return size


class MoyaRequest(Request, AttributeExposer):

    __moya_exposed_attributes__ = [
        'FILES',
        'GET',
        'POST',
        'accept',
        'accept_charset',
        'accept_encoding',
        'accept_language',
        'application_url',
        'authorization',
        'body',
        'body_file',
        'cache_control',
        'charset',
        'client_addr',
        'content_length',
        'content_type',
        'cookies',
        'date',
        'environ',
        'host',
        'host_port',
        'host_url',
        'http_version',
        'if_match',
        'if_modified_since',
        'if_none_match',
        'if_range',
        'if_unmodified_since',
        'is_body_readable',
        'is_body_seekable',
        'is_xhr',
        'json',
        'json_body',
        'max_forwards',
        'method',
        'multi',
        'params',
        'path',
        'path_qs',
        'path_url',
        'pragma',
        'query_string',
        'range',
        'referer',
        'referrer',
        'remote_addr',
        'remote_user',
        'request_body_tempfile_limit',
        'scheme',
        'server_name',
        'server_port',
        'path_info',
        'url',
        'url_encoding',
        'urlargs',
        'urlvars',
        'uscript_name',
        'user_agent'
    ]

    def __init__(self, *args, **kwargs):
        super(MoyaRequest, self).__init__(*args, **kwargs)
        self._multi = None
        self._files = None

    def __repr__(self):
        try:
            return "<moyarequest '{method} {path_info}'>".format(method=self.method,
                                                                 path_info=self.path_info)
        except:
            return "<moyarequest>"

    @property
    def multi(self):
        if self._multi is None:
            self._multi = {k: _MultiProxy(getattr(self, k), k) for k in ('GET', 'POST', 'params')}
        return self._multi

    @property
    def FILES(self):
        if self._files is None:
            self._files = {name: UploadFileProxy(field_storage) for name, field_storage in self.POST.items()
                           if isinstance(field_storage, FieldStorage)}
        return self._files

    @property
    def json(self):
        try:
            return super(MoyaRequest, self).json
        except:
            return None

    @property
    def json_body(self):
        try:
            return super(MoyaRequest, self).json_body
        except:
            return None

    def __moyaconsole__(self, console):
        console("%s %s %s" % (self.method, self.path_info, self.http_version), bold=True, fg="blue").nl()
        table = [(Cell("HTTP Header", bold=True), Cell("Value", bold=True))]
        table += sorted(self.headers.items())
        console.table(table)


class ReplaceRequest(object):
    """Contains a new request to replace current request"""

    def __init__(self, request):
        self.request = request
