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
    for name, _info in dir_fs.scandir('/', "basic", "details"):
        if wildcard.imatch_any(wildcards, name):
            continue
        info = FSInfo(_info)
        if info.is_dir:
            dirs.append(info)
        else:
            files.append(info)

    def sort_info_key(info):
        return info.name.lower()
    dirs.sort(key=sort_info_key)
    files.sort(key=sort_info_key)
    dir_list = {
        "dirs": dirs,
        "files": files,
    }
    return dir_list
