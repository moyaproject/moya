from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from fs.errors import FSError
from fs.info import Info

from .console import Cell
from .compat import text_type, implements_to_string
from .interface import AttributeExposer
from .reader import DataReader
from .context.expressiontime import ExpressionDateTime

import weakref
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

        for name, fs in sorted(self.items()):
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
            table.append([
                Cell(name),
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


class _FSInfoProxy(Info, AttributeExposer):
    __moya_exposed_attributes__ = [
        "raw",
        "namespaces",
        "name",
        "path",
        "is_dir",
        "accessed",
        "modified",
        "created",
        "metadata_changed",
        "permissions",
        "size",
    ]


class FSInfo(object):
    """Custom info class that return Moya datetime objects."""

    @classmethod
    def _from_epoch(cls, epoch):
        if epoch is None:
            return None
        return ExpressionDateTime.from_epoch(epoch)

    def __init__(self, info):
        self._info = Info.copy(info, to_datetime=self._from_epoch)

    def __moyarepr__(self, context):
        return repr(self._info)

    def __repr__(self):
        return repr(self._info)

    @property
    def raw(self):
        return self._info.raw

    @property
    def namespaces(self):
        return self._info.namespaces

    @property
    def name(self):
        return self._info.name

    @property
    def is_dir(self):
        return self._info.is_dir

    @property
    def accessed(self):
        return self._info.accessed

    @property
    def modified(self):
        return self._info.modified

    @property
    def created(self):
        return self._info.created

    @property
    def metadata_changed(self):
        return self._info.metadata_changed

    @property
    def permissions(self):
        return self._info.permissions

    @property
    def size(self):
        return self._info.size

    @property
    def type(self):
        return self._info.type

    @property
    def group(self):
        return self._info.group

    @property
    def user(self):
        return self._info.user


@implements_to_string
class FSWrapper(object):
    def __init__(self, fs, ref=False):
        self._fs = weakref.ref(fs)
        if ref:
            self.ref = self.fs

    @property
    def fs(self):
        return self._fs()

    def get_type_name(self):
        return type(self.fs).__name__

    def __str__(self):
        return self.fs.desc('/')

    def __moyarepr__(self, context):
        return text_type(self.fs)

    def __contains__(self, path):
        return self.fs.isfile(path)

    def __getitem__(self, path):
        if self.fs.isfile(path):
            return self.fs.getbytes(path)
        return self.__class__(self.fs.opendir(path), ref=True)

    def __getattr__(self, name):
        return getattr(self.fs, name)

    def __moyaconsole__(self, console):
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
