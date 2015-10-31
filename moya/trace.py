"""A container for Moya code tracebacks"""

from __future__ import print_function

from .console import Console, Cell
from .template.errors import TemplateError
from .context.expression import ExpressionError
from .context.errors import SubstitutionError
from .moyaexceptions import MoyaException
from .compat import implements_to_string, text_type
from .traceframe import Frame

import io
import sys
from operator import attrgetter
import traceback as pytraceback


_PYTHON_ERROR_TEXT = """A Python Exception may indicate either a bug in a Python extension, or Moya itself.

Consider reporting this to the Moya developers."""


@implements_to_string
class Traceback(object):

    _get_frame_compare = attrgetter('_location', 'lineno', 'libid')

    def __init__(self, url=None, method=None, handler=None, exc=None):
        self.url = url
        self.method = method
        self.handler = handler
        self.stack = []
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
        if hasattr(self.exc, '__moyaconsole__') and getattr(self.exc.__moyaconsole__, 'is_default_error_message', False):
            return None
        console = Console(html=True)
        console.obj(None, self.exc)
        return console.get_text()

    def remove_duplicates(self):
        current = None
        out = []
        for frame in self.stack:
            if current is None or self._get_frame_compare(frame) != self._get_frame_compare(current):
                out.append(frame)
                current = frame
        self.stack = out

    def add_frame(self, frame):
        self.stack.append(frame)

    def __str__(self):
        console = Console(text=True)
        self.__moyaconsole__(console)
        return console.get_text()

    def __moyaconsole__(self, console):
        stack = self.stack
        console.div("Logic Error", bold=True, fg="red")
        for frame in stack:
            console.wraptext(frame.location)
            if frame.one_line:
                console.pysnippet("\n" * (frame.lineno - 1) + frame.code, frame.lineno, extralines=0)
            elif frame.code:
                if frame.format == 'xml':
                    console.xmlsnippet(frame.code, frame.lineno, extralines=3)
                elif frame.format == 'moyatemplate':
                    start, end = frame.cols
                    console.templatesnippet(frame.code,
                                            lineno=frame.lineno,
                                            colno=start,
                                            endcolno=end)
                else:
                    console.pysnippet(frame.code, frame.lineno, extralines=3)
            console.nl()

        if self.tb:
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
        stack = context.get('._callstack', [])

    if request is not None:
        traceback = Traceback(request.path_info, request.method, exc=exc)
    else:
        traceback = Traceback(exc=exc)
    traceback.diagnosis = getattr(exc, 'diagnosis', None)

    add_pytraceback = not getattr(exc, 'hide_py_traceback', False)
    traceback.error_type = getattr(exc, 'error_type', 'internal error')

    base = context.get('.sys.base', '')

    def relativefrom(base, path):
        if base and path.startswith(base):
            path = "./" + path[len(base):]
        return path

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

    elif isinstance(exc, TemplateError):
        traceback.error_type = "Template Error"

    traceback.exception = exc
    traceback.msg = text_type(exc)
    traceback.diagnosis = traceback.diagnosis or getattr(exc, 'diagnosis', None)

    if hasattr(exc, 'get_moya_frames'):
        mf = exc.get_moya_frames()
        traceback.stack.extend(mf)

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
            one_line = False
            try:
                with io.open(filename, 'rt') as f:
                    code = f.read()
            except:
                code = text
                one_line = True

            code_path = relativefrom(base, filename)
            frame = Frame(code,
                          code_path,
                          line_number,
                          one_line=one_line,
                          obj=function_name,
                          format="python")
            traceback.add_frame(frame)
            traceback.msg = text_type(exc)
        if traceback.diagnosis is None:
            traceback.diagnosis = _PYTHON_ERROR_TEXT

    traceback.remove_duplicates()

    return traceback


def format_trace(context, stack, node, exc_info=None):
    if exc_info is None:
        exc_info = sys.exc_info()
    request = context.get('.request', None)
    moya_trace = build(context, stack, None, node, exc_info, request, py_traceback=False)
    return text_type(moya_trace)
