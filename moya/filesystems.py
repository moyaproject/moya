from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from fs.errors import FSError
from .console import Cell
from .compat import text_type, implements_to_string
from .reader import DataReader

import re

_re_fs_path = re.compile(r'^(?:\{(.*?)\})*(.*$)')


def parse_fs_path(path):
    fs_name, fs_path = _re_fs_path.match(path).groups()
    return fs_name or None, fs_path


class FSContainer(dict):

    def __moyaconsole__(self, console):
        table = [[Cell("Name", bold=True),
                  Cell("Type", bold=True),
                  Cell("Location", bold=True)]]

        list_filesystems = self.items()

        for name, fs in sorted(list_filesystems):
            syspath = fs.getsyspath('/', allow_none=True)
            if syspath is not None:
                location = syspath
                fg = "green"
            else:
                try:
                    location = fs.desc('/')
                except FSError as e:
                    location = text_type(e)
                    fg = "red"
                else:
                    fg = "blue"
            table.append([Cell(name),
                          Cell(fs.get_type_name()),
                          Cell('%s' % location, bold=True, fg=fg)
                          ])
        console.table(table, header=True)

    def close_all(self):
        for fs in self.items():
            try:
                fs.close()
            except:
                pass
        self.clear()


@implements_to_string
class FSWrapper(object):
    def __init__(self, fs):
        self.fs = fs

    def get_type_name(self):
        return type(self.fs).__name__

    def __str__(self):
        return self.fs.desc('')

    def __repr__(self):
        return repr(self.fs)

    def __contains__(self, path):
        return self.fs.isfile(path)

    def __getitem__(self, path):
        if self.fs.isfile(path):
            return self.fs.getcontents(path)
        return self.__class__(self.fs.opendir(path))

    def __getattr__(self, name):
        return getattr(self.fs, name)

    def __moyaconsole__(self, console):
        #self.fs.tree(max_levels=3)
        console((self.fs.desc('.'))).nl()
        self.fs.tree(max_levels=1)

    def keys(self):
        return self.fs.listdir()

    def values(self):
        return [self.fs.desc(p) for p in self.fs.listdir()]

    def items(self):
        return [(p, self.fs.desc(p)) for p in self.fs.listdir()]

    @property
    def reader(self):
        return DataReader(self.fs)


if __name__ == "__main__":
    print(parse_fs_path("{templates}/widgets/posts.html"))
    print(parse_fs_path("/media/css/blog.css"))
    print(parse_fs_path("{}/media/css/blog.css"))
