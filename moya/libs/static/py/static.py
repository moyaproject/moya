from __future__ import unicode_literals

import moya.expose
from moya.filesystems import FSInfo

from fs2.errors import FSError
from fs2.wildcard import imatch_any


@moya.expose.macro("get_dirlist")
def get_dirlist(app, fs, path):
    hide_wildcards = app.settings.get_list("hide")
    try:
        dir_fs = fs.opendir(path)
    except FSError:
        return None

    namespaces = ["details", "access"]
    dirlist = [
        FSInfo(resource)
        for resource in dir_fs.scandir('/', namespaces=namespaces)
        if not imatch_any(hide_wildcards, resource.name)
    ]
    return dirlist
