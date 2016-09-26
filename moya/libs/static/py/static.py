from __future__ import unicode_literals

import moya.expose
from moya.filesystems import FSInfo

from fs2.wildcard import imatch_any


@moya.expose.macro("read_directory")
def read_directory(app, fs, path):
    hide_wildcards = app.settings.get_list("hide")
    show_permissions = app.settings.get_bool('show_permissions')

    if not fs.isdir(path):
        return None

    dir_fs = fs.opendir(path)

    if show_permissions:
        namespaces = ["details", "access"]
    else:
        namespaces = ["details"]

    directory = [
        FSInfo(resource)
        for resource in dir_fs.scandir('/', namespaces=namespaces)
        if not (hide_wildcards and imatch_any(hide_wildcards, resource.name))
    ]
    return directory
