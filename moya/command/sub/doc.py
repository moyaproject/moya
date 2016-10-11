from ...command import SubCommand
from ...tools import get_moya_dir
from ... import build
from ...console import Console

from fs.path import join
from fs.opener import open_fs
from fs.tempfs import TempFS
from fs.osfs import OSFS

import sys
import os.path


class Doc(SubCommand):
    """Moya documentation"""
    help = """automatically generate Moya documentation"""

    def add_arguments(self, parser):

        parser.add_argument('--html', dest="html", action="store_true", default=False,
                            help="output should be HTML")

        subparsers = parser.add_subparsers(title="sub-commands",
                                           dest="action",
                                           help="sub command")

        extract_parser = subparsers.add_parser('extract',
                                               help="extract docs",
                                               description="Extract doc information")

        build_parser = subparsers.add_parser('build',
                                             help="build docs",
                                             description="Build extracted docs")

        view_parser = subparsers.add_parser('view',
                                            help="view docs",
                                            description="Extract and build docs, and launch the browser")

        def build_args(parser):
            # parser.add_argument('-b', '--lib', dest="lib", metavar="LONG.NAME", default=None,
            #                     help="library to generate docs for")
            parser.add_argument('-t', '--theme', dest='theme', metavar="PATH", default=None,
                                help="path to theme files (templates)")
            parser.add_argument('-s', '--source', dest="source", metavar="SOURCE", default=None,
                                help="path to extracted docs")
            parser.add_argument(dest="location", default='.', metavar="PATH",
                                help="location of library (directory containing lib.ini) or a python import if preceded by 'py:', e.g. py:moya.libs.auth")

        build_args(build_parser)
        build_args(view_parser)

        build_parser.add_argument('-o', '--output', dest="output", metavar="PATH", default=None,
                                  help="path for documentation output, defaults to ./documentation in project root")

        extract_parser.add_argument(dest="location", default=None, metavar="PATH",
                                    help="location of library (directory containing lib.ini) or a python import if preceded by 'py:', e.g. py:moya.libs.auth")

        # extract_parser.add_argument('-n', '--xmlns', dest="namespaces", metavar="XML NAMESPACE", action="append",
        #                             help="Namespace to generate docs for")
        extract_parser.add_argument('-e', '--extract', dest="extract", metavar="PATH", default=None,
                                    help="path to save raw documentation information")

        return parser

    def get_fs(self, path):
        if path is None:
            path = join(get_moya_dir(), './documentation')
        fs = open_fs(path, create=True)
        return fs

    def run(self):
        args = self.args

        _stdout = sys.stdout
        if args.html:
            self.console = Console(html=True)
            sys.stdout = self.console.make_file_interface()
            import moya
            moya.pilot.console = self.console

        try:
            action = args.action.lower()
            if action == 'extract':
                archive, lib = build.build_lib(args.location, ignore_errors=True)
                print("Extracting docs from {}...".format(lib.long_name))
                self.extract(archive, lib.long_name)

            elif action == 'build':
                if args.source is not None:
                    self.console.text("Building docs from {}...".format(args.source))
                    extract_fs = open_fs(args.source)
                else:
                    archive, lib = build.build_lib(args.location, ignore_errors=True)
                    self.console.text("Building docs for {}...".format(lib.long_name))
                    extract_fs = self.extract(archive, lib.long_name)
                return self.build(extract_fs)

            elif action == 'view':
                if args.source is not None:
                    self.console.text("Building docs from {}...".format(args.source))
                    extract_fs = open_fs(args.source)
                else:
                    archive, lib = build.build_lib(args.location, ignore_errors=True)
                    self.console.text("Building docs for {}...".format(lib.long_name))
                    extract_fs = self.extract(archive, lib.long_name)
                return self.view(archive, extract_fs)

            else:
                sys.error.write('action should be EXTRACT or BUILD\n')
                return -1
        finally:
            if args.html:
                _stdout.write(self.console.get_text() + '\n')

    def extract(self, archive, lib_name):
        args = self.args

        from ...docgen.extracter import Extracter

        if getattr(args, 'extract', None) is None:
            extract_fs = TempFS('moyadoc-{}'.format(lib_name))
        else:
            extract_fs = self.get_fs(join(args.extract, lib_name))
        extracter = Extracter(archive, extract_fs)
        extracter.extract_lib(lib_name)
        return extract_fs

    def build(self, source_fs):
        args = self.args
        output_fs = self.get_fs(args.output)

        out_path = output_fs.desc('/')

        # if not output_fs.isdirempty('/'):
        #     if raw_input('{} is not empty. Overwrite? (Y/N) '.format(out_path)).lower() not in ('y', 'yes'):
        #         sys.stdout.write('aborted\n')
        #         return -1

        if args.theme is None:
            from ... import docgen
            theme_path = os.path.join(os.path.dirname(docgen.__file__), 'themes/default')
        else:
            theme_path = args.theme
        theme_fs = self.get_fs(theme_path)

        from ...docgen.builder import Builder
        builder = Builder(source_fs, output_fs, theme_fs)
        builder.build()

    def view(self, archive, source_fs):
        args = self.args
        import tempfile
        docs_output_path = os.path.join(tempfile.tempdir, '__moyadocs__')
        output_fs = OSFS(docs_output_path, create=True)
        out_path = output_fs.desc('/')

        if args.theme is None:
            from ... import docgen
            theme_path = os.path.join(os.path.dirname(docgen.__file__), 'themes/default')
        else:
            theme_path = args.theme
        theme_fs = self.get_fs(theme_path)

        from ...docgen.builder import Builder
        builder = Builder(source_fs, output_fs, theme_fs)
        index = builder.build()
        import webbrowser
        webbrowser.open(index)
