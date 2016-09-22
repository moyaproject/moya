from __future__ import unicode_literals

import moya.expose
from moya.filesystems import FSInfo

from fs2.errors import FSError
from fs2 import wildcard


@moya.expose.macro("get_dirlist")
def get_dirlist(app, fs, path):
    wildcards = app.settings.get_list("hide")
    try:
        dir_fs = fs.opendir(path)
    except FSError:
        return None

    dirs = []
    files = []
    resources = dir_fs.scandir('/', namespaces=["details"])
    for resource in resources:
        if wildcard.imatch_any(wildcards, resource.name):
            continue
        if resource.is_dir:
            dirs.append(resource)
        else:
            files.append(resource)

    dir_list = {
        "dirs": [FSInfo(info) for info in dirs],
        "files": [FSInfo(info) for info in files],
    }
    return dir_list
