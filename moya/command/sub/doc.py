from ...command import SubCommand
from ...tools import get_moya_dir
from ... import build

from fs.path import join
from fs.opener import fsopendir
from fs.tempfs import TempFS

import sys
import os.path


class Doc(SubCommand):
    """Moya documentation"""
    help = """automatically generate Moya documentation"""

    def add_arguments(self, parser):
        parser.add_argument(dest="action", metavar="EXTRACT or BUILD",
                            help="Documentation action")

        parser.add_argument(dest="location", default=None, metavar="PATH",
                            help="location of library (directory containing lib.ini) or a python import if preceded by 'py:', e.g. py:moya.libs.auth")

        parser.add_argument('-b', '--lib', dest="lib", metavar="LONG.NAME", default=None,
                            help="library to generate docs for")
        parser.add_argument('-n', '--xmlns', dest="namespaces", metavar="XML NAMESPACE", action="append",
                            help="Namespace to generate docs for")
        parser.add_argument('-e', '--extract', dest="extract", metavar="PATH", default=None,
                            help="path to save raw documentation information")
        parser.add_argument('-o', '--output', dest="output", metavar="PATH", default=None,
                            help="path for documentation output, defaults to ./documentation in project root")
        parser.add_argument('-t', '--theme', dest='theme', metavar="PATH", default=None,
                            help="path to theme files (templates)")
        parser.add_argument('-s', '--source', dest="source", metavar="SOURCE", default=None,
                            help="path to extracted docs")

        return parser

    def get_fs(self, path):
        if path is None:
            path = join(get_moya_dir(), './documentation')
        fs = fsopendir(path, create_dir=True)
        return fs

    def run(self):
        args = self.args

        archive, lib = build.build_lib(args.location)
        archive.finalize()

        action = args.action.lower()
        if action == 'extract':
            print("Extracting {}...".format(lib.long_name))
            self.extract(archive, lib.long_name)

        elif action == 'build':
            print("Building {}...".format(lib.long_name))
            if args.source is not None:
                extract_fs = fsopendir(args.source)
            else:
                extract_fs = self.extract(archive, lib.long_name)
            return self.build(archive, extract_fs)

        else:
            sys.stdout.write('action should be EXTRACT or BUILD\n')
            return -1

    def extract(self, archive, lib_name):
        args = self.args
        namespaces = args.namespaces
        if not namespaces:
            namespaces = list(archive.known_namespaces)

        from ...docgen.extracter import Extracter

        if args.extract is None:
            extract_fs = TempFS('moyadoc-{}'.format(lib_name))
        else:
            extract_fs = self.get_fs(join(args.extract, lib_name))
        extracter = Extracter(archive, extract_fs)
        extracter.extract_lib(lib_name)
        return extract_fs

    def build(self, archive, source_fs):
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
