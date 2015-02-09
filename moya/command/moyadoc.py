from __future__ import unicode_literals
from __future__ import print_function

from .. import __version__
from .. import namespaces
from ..settings import SettingsContainer
from .. import build as moya_build

from fs.osfs import OSFS
from fs.path import join, splitext
from fs.watch import CREATED, MODIFIED, REMOVED, MOVED_DST, MOVED_SRC
from fs import utils
from fs.opener import fsopendir

import sys
import argparse
import time
from os.path import dirname, expanduser


def _notify(title, message, icon="dialog-error"):
    """Show a notification message if pynotify is available"""
    try:
        import pynotify
    except ImportError:
        return
    pynotify.init("moya-doc")
    n = pynotify.Notification(title, message, icon)
    n.show()


class ReloadChangeWatcher(object):

    def __init__(self, watch_fs, rebuild):
        self.watching_fs = watch_fs
        self.rebuild = rebuild
        self.last_build_failed = False
        self.watching_fs.add_watcher(self.on_change, '/', (CREATED, MODIFIED, REMOVED, MOVED_DST, MOVED_SRC))

    def on_change(self, event):
        ext = splitext(event.path)[1].lower()
        if ext not in ['.txt']:
            return
        print('file "{}" changed, building...'.format(event.path))
        try:
            self.rebuild()
        except Exception as e:
            _notify('moya-doc', 'Failed to build ({})'.format(e))
            import traceback
            traceback.print_exc(e)
            self.last_build_failed = True
        else:
            if self.last_build_failed:
                _notify('moya-doc', 'Build successful', icon="dialog-information")
            self.last_build_failed = False


class MoyaDoc(object):
    """Moya documentation generator"""

    builtin_namespaces = ["default",
                          "db",
                          "fs",
                          "test",
                          "email",
                          "tables",
                          "forms",
                          "auth",
                          "admin",
                          "jsonrpc",
                          "image",
                          "thumbnail",
                          "widgets",
                          "feedback",
                          "blog",
                          "comments",
                          "links",
                          "wysihtml5",
                          "recaptcha"]

    document_libs = [("moya.auth", "py:moya.libs.auth"),
                     ("moya.forms", "py:moya.libs.forms"),
                     ("moya.widgets", "py:moya.libs.widgets"),
                     ("moya.admin", "py:moya.libs.admin"),
                     ("moya.jsonrpc", "py:moya.libs.jsonrpc"),
                     ("moya.thumbnail", "py:moya.libs.thumbnail"),
                     ("moya.widgets", "py:moya.libs.widgets"),
                     ("moya.feedback", "py:moya.libs.feedback"),
                     ("moya.blog", "py:moya.libs.blog"),
                     ("moya.comments", "py:moya.libs.comments"),
                     ("moya.tables", "py:moya.libs.tables"),
                     ("moya.links", "py:moya.libs.links"),
                     ("moya.wysihtml5", "py:moya.libs.wysihtml5"),
                     ("moya.google.recaptcha", "py:moya.libs.recaptcha")]

    def get_argparse(self):
        parser = argparse.ArgumentParser(prog='moya-doc',
                                         description=self.__doc__)
        parser.add_argument("--version", dest="version", metavar="MAJOR.MINOR", default=None,
                            help="version number to build")
        parser.add_argument("--watch", dest="watch", action="store_true",
                            help="Watch source for changes and rebuild")
        parser.add_argument("--extract", "-e", dest="extract", action="store_true",
                            help="Extract tag information")
        parser.add_argument("--build", "-b", dest="build", action="store_true",
                            help="Build HTML docs")
        parser.add_argument("-no-browser", '-n', dest="nobrowser", action="store_true",
                            help="Don't launch the browser")
        parser.add_argument("-s", "--settings", dest="settings", metavar="PATH", default="~/.moyadoc",
                            help="Doc settings file")
        return parser

    def run(self):
        parser = self.get_argparse()
        args = parser.parse_args(sys.argv[1:])

        if args.version is None:
            major, minor = __version__.split('.')[:2]
            version = "{}.{}".format(major, minor)
        else:
            version = args.version

        try:
            with open(expanduser(args.settings), 'rt') as f_ini:
                cfg = SettingsContainer.read_from_file(f_ini)
                print("Read settings from {}".format(args.settings))
        except IOError:
            cfg = SettingsContainer()

        from ..docgen.extracter import Extracter
        from ..docgen.builder import Builder
        from ..command import doc_project
        location = dirname(doc_project.__file__)

        extract_fs = OSFS(join('doccode', version), create=True)
        base_docs_fs = OSFS('text')
        languages = [d for d in base_docs_fs.listdir(dirs_only=True) if len(d) == 2]

        def do_extract():
            print("Extracting docs v{}".format(version))
            utils.remove_all(extract_fs, '/')
            try:
                archive, context, doc = moya_build.build_server(location, 'settings.ini')
            except Exception:
                raise
                return -1

            extract_fs.makedir("site/docs", recursive=True)
            extract_fs.makedir("site/tags", recursive=True)
            #extract_fs.makedir("libs")

            with extract_fs.opendir('site/tags') as tags_fs:
                extracter = Extracter(archive, tags_fs)
                const_data = {}
                builtin_tags = []
                for namespace in self.builtin_namespaces:
                    xmlns = getattr(namespaces, namespace, None)
                    if xmlns is None:
                        raise ValueError("XML namespace '{}' is not in namespaces.py".format(namespace))
                    namespace_tags = archive.registry.get_elements_in_xmlns(xmlns).values()
                    builtin_tags.extend(namespace_tags)

                extracter.extract_tags(builtin_tags, const_data=const_data)

            for language in languages:
                with extract_fs.makeopendir("site/docs") as language_fs:
                    doc_extracter = Extracter(None, language_fs)
                    docs_fs = base_docs_fs.opendir(language)
                    doc_extracter.extract_site_docs(docs_fs, dirname=language)

        if args.extract:
            do_extract()

        if args.build:
            theme_path = cfg.get('paths', 'theme', None)
            dst_path = join('html', version)
            if theme_path is None:
                theme_fs = OSFS('theme')
            else:
                theme_fs = fsopendir(theme_path)

            output_path = cfg.get('paths', 'output', None)

            if output_path is None:
                output_base_fs = OSFS(dst_path, create=True)
            else:
                output_root_base_fs = fsopendir(output_path)
                output_base_fs = output_root_base_fs.makeopendir(dst_path, recursive=True)

            #output_base_fs = OSFS(join('html', version), create=True)
            utils.remove_all(output_base_fs, '/')

            def do_build():
                print("Building docs v{}".format(version))
                lib_info = {}
                lib_paths = {}
                for long_name, lib in self.document_libs:
                    lib_info[long_name] = moya_build.get_lib_info(lib)
                    lib_paths[long_name] = output_base_fs.getsyspath(join('libs', long_name, 'index.html'))
                for language in languages:
                    docs_fs = base_docs_fs.makeopendir(language)
                    output_fs = output_base_fs.makeopendir(language)
                    utils.remove_all(output_fs, '/')

                    with extract_fs.opendir("site") as extract_site_fs:
                        builder = Builder(extract_site_fs, output_fs, theme_fs)
                        from ..tools import timer
                        with timer('render time'):
                            builder.build({"libs": lib_info,
                                           "lib_paths": lib_paths})

                    # output_base_fs.makedir("libs", allow_recreate=True)
                    # for long_name, lib in self.document_libs:
                    #     source_path = extract_fs.getsyspath(join("libs", long_name))
                    #     output_path = output_base_fs.getsyspath('libs')
                    #     cmd_template = 'moya --debug doc build {} --theme libtheme --source "{}" --output "{}"'
                    #     cmd = cmd_template.format(lib, source_path, output_path)
                    #     os.system(cmd)

            def extract_build():
                do_extract()
                do_build()

            do_build()

            if not args.nobrowser:
                import webbrowser
                webbrowser.open(output_base_fs.getsyspath('en/index.html'))

            if args.watch:
                print("Watching for changes...")
                watcher = ReloadChangeWatcher(base_docs_fs, extract_build)
                while 1:
                    try:
                        time.sleep(0.1)
                    except:
                        break

        return 0
