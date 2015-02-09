from __future__ import print_function
from __future__ import unicode_literals
from __future__ import absolute_import

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...console import Cell
from ...compat import text_type, raw_input

from fs.opener import fsopendir
from fs.errors import FSError
from fs.multifs import MultiFS
from fs.mountfs import MountFS

import os


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
        parser.add_argument("--tree", dest="tree", nargs='?', default=None, const='/',
                            help="display a tree view of the filesystem")
        parser.add_argument("--cat", dest="cat", default=None, metavar="PATH",
                            help="Cat a file to the console")
        parser.add_argument("--syspath", dest="syspath", default=None, metavar="PATH",
                            help="display the system path of a file")
        parser.add_argument("--open", dest="open", default=None, metavar="PATH",
                            help="open a file")
        parser.add_argument("--copy", dest="copy", metavar="PATH", nargs='+',
                            help="copy contents of filesystem to PATH")
        parser.add_argument("-f", "--force", dest="force", action="store_true", default=False,
                            help="force overwrite of destination even if it is not empty (with --copy)")
        return parser

    def run(self):
        args = self.args
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      args.server)
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
            with fs.opendir(args.tree) as tree_fs:
                tree_fs.tree()
            return

        if args.listdir:
            if fs is None:
                self.console.error("Filesystem required")
                return -1
            for path in fs.opendir(args.listdir).listdir():
                if fs.isdir(path):
                    self.console(path, fg="cyan", bold=True).nl()
                else:
                    self.console(path).nl()

        elif args.cat:
            if fs is None:
                self.console.error("Filesystem required")
                return -1
            contents = fs.getcontents(args.cat)
            self.console.cat(contents, args.cat)

        elif args.open:
            if fs is None:
                self.console.error("Filesystem required")
                return -1

            filepath = fs.getsyspath(args.open, allow_none=True)
            if filepath is None:
                self.console.error("No system path for '%s' in filesystem '%s'" % (args.open, args.fs))
                return -1

            import subprocess
            if os.name == 'mac':
                subprocess.call(('open', filepath))
            elif os.name == 'nt':
                subprocess.call(('start', filepath), shell=True)
            elif os.name == 'posix':
                subprocess.call(('xdg-open', filepath))
            else:
                self.console.error("Don't know how to open files on this platform (%s)" % os.name)

        elif args.syspath:
            if fs is None:
                self.console.error("Filesystem required (use -cat FILESYSTEM)")
                return -1
            if not fs.exists(args.syspath):
                self.console.error("No file called '%s' found in filesystem '%s'" % (args.syspath, args.fs))
                return -1
            syspath = fs.getsyspath(args.syspath, allow_none=True)
            if syspath is None:
                self.console.error("No system path for '%s' in filesystem '%s'" % (args.syspath, args.fs))
            else:
                self.console(syspath).nl()

        elif args.copy:
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
                dst_fs = fsopendir(dst, create_dir=True)

                if not args.force and not dst_fs.isdirempty('/'):
                    response = raw_input("'%s' is not empty. Copying may overwrite directory contents. Continue? " % dst)
                    if response.lower() not in ('y', 'yes'):
                        return 0

                from fs.utils import copydir
                copydir(src_fs, dst_fs)
            else:
                with fs.open(src, 'rb') as read_f:
                    with open(dst, 'wb') as write_f:
                        while 1:
                            chunk = read_f.read(16384)
                            if not chunk:
                                break
                            write_f.write(chunk)

        else:
            table = [[Cell("Name", bold=True),
                      Cell("Type", bold=True),
                      Cell("Location", bold=True)]]

            if fs is None:
                list_filesystems = filesystems.items()
            else:
                list_filesystems = [(args.fs, fs)]

            for name, fs in sorted(list_filesystems):

                if isinstance(fs, MultiFS):
                    location = '\n'.join(mount_fs.desc('/') for mount_fs in fs.fs_sequence)
                    fg = "yellow"
                elif isinstance(fs, MountFS):
                    mount_desc = []
                    for path, dirmount in fs.mount_tree.items():
                        mount_desc.append('%s->%s' % (path, dirmount.fs.desc('/')))
                    location = '\n'.join(mount_desc)
                    fg = "magenta"
                else:
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
                             Cell(type(fs).__name__),
                             Cell(location, bold=True, fg=fg)
                              ])
            self.console.table(table, header=True)
