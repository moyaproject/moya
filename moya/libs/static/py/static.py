from __future__ import unicode_literals

import moya.expose
from moya.filesystems import FSInfo

from fs2.errors import FSError
from fs2.wildcard import imatch_any


@moya.expose.macro("get_dirlist")
def get_dirlist(app, fs, path):
    wildcards = app.settings.get_list("hide")
    try:
        dir_fs = fs.opendir(path)
    except FSError:
        return None

    dirs = []
    files = []
    for resource in dir_fs.scandir('/', namespaces=["details", 'access']):
        if not imatch_any(wildcards, resource.name):
            _resource = FSInfo(resource)
            if resource.is_dir:
                dirs.append(_resource)
            else:
                files.append(_resource)

    return {
        "dirs": dirs,
        "files": files,
    }
