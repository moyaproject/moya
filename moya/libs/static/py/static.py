from __future__ import unicode_literals

from six import text_type

import moya.expose
from moya.filesystems import FSInfo

from fs.errors import PermissionDenied, FSError
from fs.wildcard import imatch_any


@moya.expose.macro("read_directory")
def read_directory(app, fs, path, permissions=True, links=False):
    if not fs.isdir(path):
        return None
    hide_wildcards = app.settings.get_list("hide")
    namespaces = ['details']
    if permissions:
        namespaces.append('access')
    if links:
        namespaces.append('link')
    try:
        dir_fs = fs.opendir(path)
        directory = [
            FSInfo(resource)
            for resource in dir_fs.scandir('/', namespaces=namespaces)
            if not (hide_wildcards and imatch_any(hide_wildcards, resource.name))
        ]
    except PermissionDenied:
        app.throw(
            'moya.static.permission-denied',
            'no permission to read {}'.format(path)
        )
    except FSError as error:
        app.log.exception('error reading directory %s', path)
        app.throw(
            'moya.static.fs-error',
            text_type(error)
        )
    return {'fs': dir_fs, "directory": directory}
