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
        resource = FSInfo(resource)
        if resource.is_dir:
            dirs.append(resource)
        else:
            files.append(resource)

    def sort_info_key(info):
        return info.name.lower()
    dirs.sort(key=sort_info_key)
    files.sort(key=sort_info_key)
    dir_list = {
        "dirs": dirs,
        "files": files,
    }
    return dir_list
