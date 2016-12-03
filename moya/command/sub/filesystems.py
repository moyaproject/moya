from __future__ import print_function
from __future__ import unicode_literals
from __future__ import absolute_import

import os
import sys

from fs.opener import open_fs
from fs.errors import FSError, NoSysPath
from fs.multifs import MultiFS
from fs.mountfs import MountFS
from fs.path import dirname
from fs import tree

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...console import Cell
from ...compat import text_type, raw_input


def _ls(console, file_paths, dir_paths, format_long=False):
    """Cannibalized from pyfileystem"""

    dirs = frozenset(dir_paths)
    paths = sorted(file_paths + dir_paths, key=lambda p: p.lower())

    def columnize(paths, num_columns):
        col_height = (len(paths) + num_columns - 1) / num_columns
        columns = [[] for _ in range(num_columns)]
        col_no = 0
        col_pos = 0
        for path in paths:
            columns[col_no].append(path)
            col_pos += 1
            if col_pos >= col_height:
                col_no += 1
                col_pos = 0

        padded_columns = []

        def wrap(path):
            return (path in dirs, path.ljust(max_width))

        for column in columns:
            if column:
                max_width = max([len(path) for path in column])
            else:
                max_width = 1
            max_width = min(max_width, terminal_width)
            padded_columns.append([wrap(path) for path in column])

        return padded_columns

    def condense_columns(columns):
        max_column_height = max([len(col) for col in columns])
        lines = [[] for _ in range(max_column_height)]
        for column in columns:
            for line, (isdir, path) in zip(lines, column):
                line.append((isdir, path))
        for line in lines:
            for i, (isdir, path) in enumerate(line):
                if isdir:
                    console(path, bold=True, fg="blue")
                else:
                    console(path)
                if i < len(line) - 1:
                    console('  ')
            console.nl()

    if format_long:
        for path in paths:
            if path in dirs:
                console(path, bold=True, fg="blue")
            else:
                console(path)
            console.nl()

    else:
        terminal_width = console.width
        path_widths = [len(path) for path in paths]
        smallest_paths = min(path_widths)
        num_paths = len(paths)

        num_cols = min(terminal_width // (smallest_paths + 2), num_paths)
        while num_cols:
            col_height = (num_paths + num_cols - 1) // num_cols
            line_width = 0
            for col_no in range(num_cols):
                try:
                    col_width = max(path_widths[col_no * col_height: (col_no + 1) * col_height])
                except ValueError:
                    continue
                line_width += col_width
                if line_width > terminal_width:
                    break
                line_width += 2
            else:
                if line_width - 1 <= terminal_width:
                    break
            num_cols -= 1
        num_cols = max(1, num_cols)
        columns = columnize(paths, num_cols)
        condense_columns(columns)


class FS(SubCommand):
    """Manage project filesystems"""
    help = "manage project fsfilesystems"

    def add_arguments(self, parser):
        parser.add_argument(dest="fs", nargs="?", default=None, metavar="FILESYSTEM",
                            help="filesystem name")
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to project settings")
        parser.add_argument("--server", dest="server", default='main', metavar="SERVERREF",
                            help="server element to use")
        parser.add_argument('--ls', dest="listdir", default=None, metavar="PATH",
                            help="list files / directories")
        parser.add_argument("--tree", dest="tree", default=None,
                            help="display a tree view of the filesystem")
        parser.add_argument("--cat", dest="cat", default=None, metavar="PATH",
                            help="Cat a file to the console")
        parser.add_argument("--syspath", dest="syspath", default=None, metavar="PATH",
                            help="display the system path of a file")
        parser.add_argument("--open", dest="open", default=None, metavar="PATH",
                            help="open a file")
        parser.add_argument("--copy", dest="copy", metavar="DESTINATION or PATH DESTINATION", nargs='+',
                            help="copy contents of a filesystem to PATH, or a file from PATH to DESTINATION")
        parser.add_argument('--extract', dest="extract", metavar="PATH DIRECTORY", nargs=2,
                            help="copy a file from a filesystem, preserving directory structure")
        parser.add_argument("-f", "--force", dest="force", action="store_true", default=False,
                            help="force overwrite of destination even if it is not empty (with --copy)")
        parser.add_argument("--serve", dest="serve", default=None, action="store_true",
                            help="statically serve a filesystem")
        parser.add_argument('--host', dest='host', default='127.0.0.1',
                            help="server host (with --serve)")
        parser.add_argument('-p', '--port', default='8000',
                            help="server port (with --serve)")
        return parser

    def run(self):
        args = self.args
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      args.server,
                                      disable_autoreload=True,
                                      master_settings=self.master_settings)
        archive = application.archive

        filesystems = archive.filesystems

        fs = None
        if args.fs:
            try:
                fs = filesystems[args.fs]
            except KeyError:
                self.console.error("No filesystem called '%s'" % args.fs)
                return -1

        if args.tree is not None:
            if fs is None:
                self.console.error("Filesystem required")
                return -1
            with fs.opendir(args.tree or '/') as tree_fs:
                tree.render(tree_fs, max_levels=None)
            return

        if args.listdir:
            if fs is None:
                self.console.error("Filesystem required")
                return -1

            dir_fs = fs.opendir(args.listdir)
            file_paths = []
            dir_paths = []
            for info in dir_fs.scandir('/'):
                if info.is_dir:
                    dir_paths.append(info.name)
                else:
                    file_paths.append(info.name)

            _ls(self.console, file_paths, dir_paths)

        elif args.cat:
            if fs is None:
                self.console.error("Filesystem required")
                return -1
            contents = fs.getbytes(args.cat)
            self.console.cat(contents, args.cat)

        elif args.open:
            if fs is None:
                self.console.error("Filesystem required")
                return -1

            try:
                filepath = fs.getsyspath(args.open)
            except NoSysPath:
                self.console.error("No system path for '%s' in filesystem '%s'" % (args.open, args.fs))
                return -1

            import subprocess
            system = sys.platform
            if system == 'darwin':
                subprocess.call(('open', filepath))
            elif system == 'win32':
                subprocess.call(('start', filepath), shell=True)
            elif system == 'linux2':
                subprocess.call(('xdg-open', filepath))
            else:
                self.console.error("Moya doesn't know how to open files on this platform (%s)" % os.name)

        elif args.syspath:
            if fs is None:
                self.console.error("Filesystem required")
                return -1
            if not fs.exists(args.syspath):
                self.console.error("No file called '%s' found in filesystem '%s'" % (args.syspath, args.fs))
                return -1
            try:
                syspath = fs.getsyspath(args.syspath)
            except NoSysPath:
                self.console.error("No system path for '%s' in filesystem '%s'" % (args.syspath, args.fs))
            else:
                self.console(syspath).nl()

        elif args.copy:
            if fs is None:
                self.console.error("Filesystem required")
                return -1
            if len(args.copy) == 1:
                src = '/'
                dst = args.copy[0]
            elif len(args.copy) == 2:
                src, dst = args.copy
            else:
                self.console.error("--copy requires 1 or 2 arguments")
                return -1

            if fs.isdir(src):
                src_fs = fs.opendir(src)
                from fs.copy import copy_dir
                with open_fs(dst, create=True) as dst_fs:
                    if not args.force and not dst_fs.isempty('/'):
                        response = raw_input("'%s' is not empty. Copying may overwrite directory contents. Continue? " % dst)
                        if response.lower() not in ('y', 'yes'):
                            return 0
                    copy_dir(src_fs, '/', dst_fs, '/')
            else:
                with fs.open(src, 'rb') as read_f:
                    if os.path.isdir(dst):
                        dst = os.path.join(dst, os.path.basename(src))
                    try:
                        os.makedirs(dst)
                        with open(dst, 'wb') as write_f:
                            while 1:
                                chunk = read_f.read(16384)
                                if not chunk:
                                    break
                                write_f.write(chunk)
                    except IOError as e:
                        self.error('unable to write to {}'.format(dst))

        elif args.extract:
            if fs is None:
                self.console.error("Filesystem required")
                return -1
            src_path, dst_dir_path = args.extract
            src_fs = fs
            dst_fs = open_fs(dst_dir_path, create=True)

            if not args.force and dst_fs.exists(src_path):
                response = raw_input("'%s' exists. Do you want to overwrite? " % src_path)
                if response.lower() not in ('y', 'yes'):
                    return 0

            dst_fs.makedirs(dirname(src_path), recreate=True)
            with src_fs.open(src_path, 'rb') as read_file:
                dst_fs.setfile(src_path, read_file)

        elif args.serve:

            from .serve import Serve
            Serve.run_server(
                args.host,
                args.port,
                fs,
                show_access=True,
                develop=False,
                debug=True
            )

        else:
            table = [[Cell("Name", bold=True),
                      Cell("Type", bold=True),
                      Cell("Location", bold=True)]]

            if fs is None:
                list_filesystems = filesystems.items()
            else:
                list_filesystems = [(args.fs, fs)]

            def get_type_name(name):
                name = type(fs).__name__
                return name[:-2].lower() if name.endswith('FS') else name.lower()

            for name, fs in sorted(list_filesystems):
                if isinstance(fs, MultiFS):
                    location = '\n'.join(mount_fs.desc('/') for name, mount_fs in fs.iterate_fs())
                    fg = "yellow"
                elif isinstance(fs, MountFS):
                    mount_desc = []
                    for path, dirmount in fs.mount_tree.items():
                        mount_desc.append('%s->%s' % (path, dirmount.fs.desc('/')))
                    location = '\n'.join(mount_desc)
                    fg = "magenta"
                else:
                    try:
                        syspath = fs.getsyspath('/')
                    except NoSysPath:
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
                    Cell(get_type_name(fs)),
                    Cell(location, bold=True, fg=fg)
                ])
            self.console.table(table, header=True)
