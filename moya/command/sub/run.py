from __future__ import unicode_literals
from __future__ import print_function

from ...command import SubCommand
from ...archive import Archive
from ...context import Context
from ...tools import timer
from ... import errors
from ... import namespaces
from ...compat import text_type
from ...context.expressiontime import ExpressionDateTime
from ...__init__ import pilot
from ...timezone import Timezone

import os
import os.path
import sys


class Run(SubCommand):
    """Invoke Moya XML code"""
    help = "invoke Moya XML code"

    def add_arguments(self, parser):
        parser.add_argument(dest="path", metavar="FILE",
                            help="path to XML file")
        parser.add_argument("-e", dest="elementref", metavar="ELEMENTREF", default="main",
                            help="element reference to invoke (default is 'main')")
        parser.add_argument("--time", dest="timer", default=False, action="store_true",
                            help="report time taken")
        parser.add_argument("-b", "--breakpoint", action="store_true", default=False,
                            help="start debugging at first element")
        parser.add_argument("-t", dest="templatedir", default=None,
                            help="Set the template directory")
        parser.add_argument('--let', dest='params', nargs="*",
                            help="parameters in the form foo=bar")
        parser.add_argument('--logging', dest="logging", default=None,
                            help="logging conf")
        return parser

    def run(self):
        args = self.args

        from fs import opener
        fs, fspath = opener.open(args.path)

        from ...loggingconf import init_logging
        if args.logging and os.path.exists(args.logging):
            init_logging(args.logging)

        archive = Archive()
        lib = archive.create_library(long_name="moya.run", namespace=namespaces.run)
        if not lib.import_document(fs, fspath):
            for failed_doc in lib.failed_documents:
                self.console.document_error(failed_doc.msg,
                                            failed_doc.path,
                                            failed_doc.code,
                                            failed_doc.line,
                                            failed_doc.col)
            return -1
        app = archive.create_app('run', 'moya.run')
        c = Context()
        c['.console'] = self.console
        c['.app'] = app
        c['.now'] = ExpressionDateTime.utcnow()
        try:
            c['tz'] = Timezone(os.environ['TZ'])
        except KeyError:
            pass

        import locale
        _locale, encoding = locale.getdefaultlocale()
        c['.locale'] = _locale

        params = {}
        if args.params:
            for p in args.params:
                if '=' not in p:
                    sys.stderr.write("{} is not in the form <name>=<expression>\n".format(p))
                    return -1
                k, v = p.split('=', 1)
                params[k] = v

        if args.templatedir is not None:
            archive.init_template_engine('moya', {})
            archive.init_templates('default', args.templatedir, 100)

        console = self.console
        try:
            archive.build_libs()
        except errors.ParseError as e:
            line, col = e.position
            console.document_error(text_type(e),
                                   e.path,
                                   e._code,
                                   line,
                                   col)
            return None
        except errors.ElementError as element_error:
            line = element_error.source_line
            col = None
            console.document_error(text_type(element_error),
                                   element_error.element._location,
                                   element_error.element._code,
                                   line,
                                   col)
            raise errors.StartupFailedError('Failed to build project')

        call = archive.get_callable_from_document(fspath,
                                                  args.elementref,
                                                  fs=fs,
                                                  breakpoint=args.breakpoint,
                                                  archive=archive,
                                                  lib=lib)

        if call is None:
            raise ValueError("Element reference '%s' not found in document" % args.elementref)
        try:
            with pilot.manage_request(None, c):
                if args.timer:
                    with timer():
                        call(c, **params)
                else:
                    call(c, **params)
        except Exception as e:
            console.obj(c, e)
