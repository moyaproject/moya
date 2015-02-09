"""A container for Moya code tracebacks"""

from __future__ import print_function

from . import syntax
from .console import Console, Cell
from .template.errors import (TagError,
                                  RenderError,
                                  TemplateError,
                                  MissingTemplateError)
from .context.expression import ExpressionError
from .context.errors import SubstitutionError
from .logic import MoyaException
from .compat import implements_to_string, text_type

import io
import sys
import traceback as pytraceback


_PYTHON_ERROR_TEXT = """A Python Exception may indicate either a bug in a Python extension, or Moya itself.

Consider reporting this to the Moya developers."""


class Frame(object):
    def __init__(self,
                 code,
                 location,
                 lineno,
                 path=None,
                 obj=None,
                 cols=None,
                 one_line=False,
                 code_start=1,
                 libid=None,
                 format="xml",
                 raw_location=None):
        self.code = code
        self._location = location
        self.lineno = lineno
        self.obj = obj
        self.cols = cols
        self.one_line = one_line
        self.code_start = code_start
        self.format = format
        self.libid = libid
        self._raw_location = raw_location

    @property
    def location(self):
        if self.obj:
            return 'File "%s", line %s, in %s' % (self._location, self.lineno, self.obj)
        else:
            if self.cols:
                return 'File "%s", line %s, col %s' % (self._location, self.lineno, self.cols[0])
            else:
                return 'File "%s"' % (self._location, self.lineno)

    @property
    def raw_location(self):
        return self._raw_location or self._location

    @property
    def snippet(self):
        try:
            if not self.code:
                return ''
            if self.one_line:
                return self.code
            return syntax.highlight(self.format,
                                    self.code,
                                    self.lineno - 3,
                                    self.lineno + 3,
                                    highlight_lines=[self.lineno],
                                    highlight_range=[self.lineno, self.cols[0], self.cols[1]] if self.cols else None)
        except Exception as e:
            raise
            from traceback import print_exc
            print_exc(e)


@implements_to_string
class Traceback(object):
    def __init__(self, url=None, method=None, handler=None, exc=None):
        self.url = url
        self.method = method
        self.handler = handler
        self.moyastack = []
        self.pystack = []
        self.exception = None
        self.tb = None
        self.error_message = None
        self.exc = exc
        self.exc_info = None
        self.msg = None
        self.error_type = "internal error"
        self._displayed = False
        self.diagnosis = getattr('exc', 'diagnosis', None)

    @property
    def console_error(self):
        console = Console(html=True)
        console.obj(None, self.exc)
        return console.get_text()

    def add_frame(self, frame):
        self.moyastack.append(frame)

    def add_pyframe(self, frame):
        self.pystack.append(frame)

    @property
    def stack(self):
        return self.moyastack + self.pystack

    def __str__(self):
        console = Console(text=True)
        self.__moyaconsole__(console)
        return console.get_text()

    def __moyaconsole__(self, console):
        stack = (self.moyastack)
        console.div("Logic Error", bold=True, fg="red")
        for frame in stack:
            console.text(frame.location)
            if frame.one_line:
                console.text("    " + frame.code)
            elif frame.code:
                console.xmlsnippet(frame.code, frame.lineno, extralines=2)
        if self.tb:
            console.nl()
            console.exception(self.tb, tb=True)
        else:
            console.error(self.msg)
        if self.diagnosis:
            console.table([[Cell(self.diagnosis, italic=True)]])
        console.div()


def build(context, stack, node, exc, exc_info, request, py_traceback=True):
    add_pytraceback = True
    if node is not None:
        node = getattr(node, 'node', node)
    if stack is None:
        stack = context.get('.callstack', [])

    if request is not None:
        traceback = Traceback(request.path_info, request.method, exc=exc)
    else:
        traceback = Traceback(exc=exc)
    traceback.diagnosis = getattr(exc, 'diagnosis', None)

    add_pytraceback = not getattr(exc, 'hide_py_traceback', False)
    traceback.error_type = getattr(exc, 'error_type', 'internal error')

    for s in stack:
        e = getattr(s, 'element', None)
        if e and e._code:
            frame = Frame(e._code,
                          e._location,
                          e.source_line or 1,
                          obj=text_type(e),
                          libid=e.libid)
            traceback.add_frame(frame)

    element = getattr(exc, 'element', None)

    if element is not None and hasattr(element.document, 'structure'):
        frame = Frame(element.document.structure.xml,
                      element._location,
                      element.source_line or 1,
                      obj=text_type(element),
                      libid=element.libid)
        traceback.add_frame(frame)
        add_pytraceback = False

    elif hasattr(node, '_location') and hasattr(node, 'source_line'):
        if node._code:
            frame = Frame(node._code,
                          node._location,
                          node.source_line or 1,
                          obj=text_type(node),
                          libid=node.libid)
            traceback.add_frame(frame)

    if isinstance(exc, MoyaException):
        traceback.error_type = "Moya Exception"
        traceback.moya_exception_type = exc.type
        add_pytraceback = False

    elif isinstance(exc, ExpressionError):
        traceback.error_type = "Expression Error"
        add_pytraceback = False

    elif isinstance(exc, SubstitutionError):
        traceback.error_type = "Substitution Error"
        add_pytraceback = False

    elif isinstance(exc, RenderError):
        traceback.error_type = "Template Render Error"
        if hasattr(exc, 'template_stack'):
            for ts in exc.template_stack[:-1]:
                if 'node' in ts:
                    node = ts['node']
                    frame = Frame(node.code,
                                  node.template.path,
                                  node.location[0],
                                  raw_location=node.template.raw_path,
                                  cols=node.location[1:],
                                  format="moyatemplate")
                    traceback.add_frame(frame)
        frame = Frame(exc.code,
                      exc.path,
                      exc.lineno,
                      raw_location=getattr(exc, 'raw_path', None),
                      cols=(exc.start, exc.end),
                      format="moyatemplate")
        traceback.add_frame(frame)
        add_pytraceback = False
        if exc.original:
            exc = exc.original
            if isinstance(exc, (TagError,
                                ExpressionError,
                                SubstitutionError,
                                MissingTemplateError)):
                add_pytraceback = False

    elif isinstance(exc, TemplateError):
        traceback.error_type = "Template Error"
        frame = Frame(exc.code,
                      exc.path,
                      raw_location=exc.raw_path,
                      lineno=exc.lineno,
                      cols=(exc.start, exc.end),
                      format="moyatemplate")
        traceback.add_frame(frame)
        add_pytraceback = False

    traceback.exception = exc
    traceback.msg = text_type(exc)
    traceback.diagnosis = traceback.diagnosis or getattr(exc, 'diagnosis', None)

    if context.get('.develop', False):
        add_pytraceback = True
    if add_pytraceback and exc_info and py_traceback:
        traceback.error_type = "Python Exception"
        tb_type, tb_value, tb = exc_info
        traceback.tb = ''.join(pytraceback.format_exception(tb_type, tb_value, tb))

        pyframes = pytraceback.extract_tb(tb)

        for i, f in enumerate(reversed(pyframes)):
            if f[2] == 'logic':
                pyframes = pyframes[len(pyframes) - i - 1:]
                break

        for (filename, line_number, function_name, text) in pyframes:
            try:
                with io.open(filename, 'rt') as f:
                    code = f.read()
            except:
                code = None
            frame = Frame(code,
                          filename,
                          line_number,
                          one_line=False,
                          obj=function_name,
                          format="python")
            traceback.add_pyframe(frame)
            traceback.msg = text_type(exc)
        if traceback.diagnosis is None:
            traceback.diagnosis = _PYTHON_ERROR_TEXT

    return traceback


def format_trace(context, stack, node, exc_info=None):
    if exc_info is None:
        exc_info = sys.exc_info()
    request = context.get('.request', None)
    moya_trace = build(context, stack, None, node, exc_info, request, py_traceback=False)
    return text_type(moya_trace)
