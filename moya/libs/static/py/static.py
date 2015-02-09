from __future__ import unicode_literals

import moya
from moya.compat import string_types

from fs.errors import FSError

import fnmatch
import re


@moya.expose.macro("get_dirlist")
def get_dirlist(app, fs, path):
    wildcards = app.settings.get_list("hide")
    try:
        dir_fs = fs.opendir(path)
    except FSError:
        return None

    wildcard = lambda f: True
    if wildcards:
        if isinstance(wildcards, string_types):
            wildcards = [wildcards]
        match = re.compile('|'.join(fnmatch.translate(wc) for wc in wildcards), re.UNICODE).match
        wildcard = lambda f: not match(f)

    dirs = dir_fs.listdirinfo(dirs_only=True, wildcard=wildcard)
    files = dir_fs.listdirinfo(files_only=True, wildcard=wildcard)

    ret = {'dirs': sorted(dirs, key=lambda i: i[0].lower()),
           'files': sorted(files, key=lambda i: i[0].lower())}
    return ret
