from __future__ import unicode_literals

import moya.expose
from moya.filesystems import FSInfo

from fs.wildcard import imatch_any


@moya.expose.macro("read_directory")
def read_directory(app, fs, path, permissions=True):
    if not fs.isdir(path):
        return None
    hide_wildcards = app.settings.get_list("hide")
    namespaces = ['details', 'access'] if permissions else ['details']
    dir_fs = fs.opendir(path)
    directory = [
        FSInfo(resource)
        for resource in dir_fs.scandir('/', namespaces=namespaces)
        if not (hide_wildcards and imatch_any(hide_wildcards, resource.name))
    ]
    return directory
