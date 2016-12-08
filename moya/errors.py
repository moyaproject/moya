from __future__ import unicode_literals
from __future__ import print_function

from .compat import text_type, implements_to_string
from .tools import textual_list


class ArchiveError(Exception):
    """Error occurred with an archive operation"""


class LogicError(Exception):
    hide_py_traceback = True
    error_type = "Logic Error"

    def __init__(self, original, trace):
        self.original = original
        self.moya_trace = trace
        super(LogicError, self).__init__(trace.msg)

    @property
    def diagnosis(self):
        return getattr(self.original, 'diagnosis', None)

    def get_moya_frames(self):
        return self.moya_trace.stack

    def __moyaconsole__(self, console):
        self.moya_trace.__moyaconsole__(console)

    def __unicode__(self):
        return self.moya_trace.msg

    def __repr__(self):
        return "<LogicError {}>".format(self.moya_trace.msg)


class MoyaError(Exception):
    """Base exception for Moya related errors"""

    # The message to use if no error is supplied
    default_message = ""
    # The message to user if an error is supplied
    message = "{error}"

    def _escape_format(cls, text):
        return text.replace('{', '{{').replace('}', '}}')

    def __init__(self, error=None, **kwargs):
        fmt_args = kwargs
        fmt_args['error'] = error
        msg = self.format_error(error, fmt_args)
        if 'diagnosis' in kwargs:
            self.diagnosis = kwargs['diagnosis']
        super(MoyaError, self).__init__(msg)

    def format_error(self, error, fmt_args):
        if fmt_args:
            fmt_args = {k: self._escape_format(text_type(v)) for k, v in fmt_args.items()}
        if error is None:
            msg = self.default_message.format(**fmt_args)
        else:
            # print error, repr(fmt_args)
            # error = self._escape_format(error)
            fmt_args['error'] = error.format(**fmt_args)
            msg = self.message.format(**fmt_args)
        return msg

    def __moyaconsole__(self, console):
        console.text(text_type(self))
    __moyaconsole__.is_default_error_message = True

    # def __unicode__(self):
    #     if self.fmt is None:
    #         return super(MoyaError, self).__unicode__()
    #     else:
    #         return self.fmt.format(**self.get_fmt_dict())

    # def __str__(self):
    #     if self.fmt is None:
    #         return super(MoyaError, self).__str__()
    #     else:
    #         return self.fmt.format(**self.get_fmt_dict()).encode('ascii', 'replace')


class ParseError(MoyaError):
    def __init__(self, message, path="?", position=None, code=None):
        super(ParseError, self).__init__(message)
        self.path = path
        line, col = position
        self.position = position
        self.line = line
        self.col = col
        self.code = code

    def render(self, colour=False):
        line, col = self.position
        lines = self.code.replace('\t', ' ' * 4).splitlines()
        start = max(0, line - 3)
        end = min(len(lines), line + 2)
        showlines = lines[start:end]

        linenos = [str(n + 1) for n in range(start, end)]
        maxline = max(len(l) for l in linenos)

        errorlines = []
        highlight_line = str(line)
        for lineno, line in zip(linenos, showlines):
            if lineno == highlight_line:
                fmt = "*%s %s"
            else:
                fmt = " %s %s"
            errorlines.append(fmt % (lineno.ljust(maxline), line))

        print('\n'.join(errorlines))


@implements_to_string
class DocumentError(MoyaError):
    """Raised when there is an error constructing the document"""
    def __init__(self, element, msg=''):
        super(DocumentError, self).__init__()
        self.element = element
        self.msg = msg

    def __repr__(self):
        return '%s in %s' % (self.msg, self.element)


class AttributeError(MoyaError):
    """An attribute related parse error"""
    hide_py_traceback = True
    error_type = "Attribute error"


class BadValueError(MoyaError):
    hide_py_traceback = True
    error_type = "Invalid attribute error"


@implements_to_string
class ElementError(MoyaError):
    error_type = "Element error"
    hide_py_traceback = True

    def __init__(self, msg=None, element=None, diagnosis=None):
        self.msg = msg
        self.element = element
        self.diagnosis = diagnosis
        super(ElementError, self).__init__(msg)

    @property
    def source_line(self):
        if self.element:
            return getattr(self.element, 'source_line', None)
        return None

    def get_message(self):
        if self.element is None:
            return self.msg
        #path = self.element._document.path
        #line = self.element.source_line or '?'
        return 'in {}, {}'.format(self.element, self.msg)
        # return 'Document "%s", line %s, in <%s>: %s' % (path,
        #                                                 line,
        #                                                 self.element._tag_name,
        #                                                 self.msg)

    def __str__(self):
        return text_type(self.get_message())


class ContentError(ElementError):
    error_type = "Content Error"


class ElementNotFoundError(MoyaError):
    default_message = "element '{elementref}' was not found in the project"
    hide_py_traceback = True
    error_type = "Element not found error"

    def __init__(self, elementref, app=None, lib=None, msg=None, reason=None):
        if isinstance(elementref, tuple):
            xmlns, ref = elementref
            elementref = "{{" + xmlns + "}}" + ref
        self.elementref = elementref
        self.app = app
        self.lib = lib
        diagnosis = None
        if msg is None:
            if self.elementref and '#' not in self.elementref:
                diagnosis = """\
Did you mean **"#{elementref}"** ?

Without the '#' symbol, Moya will look for the element with **docname="{elementref}"** in the current *file*.

Add a # if you meant to reference an element in the current *application*.
""".format(elementref=self.elementref)
            if app or lib:
                msg = "unable to reference element '{elementref}' in {obj}".format(elementref=self.elementref,
                                                                         obj=self.app or self.lib,)
            else:
                msg = "unable to reference element '{elementref}'".format(elementref=self.elementref)
        else:
            msg = msg.replace('{', '{{').replace('}', '}}')
        if reason is not None:
            msg = "{} ({})".format(msg, reason)
        super(ElementNotFoundError, self).__init__(msg, elementref=elementref, diagnosis=diagnosis)

    # def get_message(self):
    #     if not (self.app or self.lib):
    #         return super(ElementNotFoundError, self).get_message()
    #     return "element '{elementref}' not found in {obj}".format(elementref=self.elementref,
    #                                                               obj=self.app or self.lib)


class UnknownLibraryError(MoyaError):
    default_message = "library '{lib}' must be imported before it can be installed"
    hide_py_traceback = True
    error_type = "Library not imported error"

    def __init__(self, lib):
        self.lib = lib
        super(UnknownLibraryError, self).__init__(lib=lib)


class UnknownElementError(MoyaError):
    default_message = "element {{{xmlns}}}{element} is not recognized"

    def __init__(self, xmlns, element, source_line=None):
        self.xmlns = xmlns
        self.element = element
        self.source_line = source_line
        super(UnknownElementError, self).__init__(xmlns=xmlns, element=element)


class AmbiguousFilterError(MoyaError):
    default_message = "filter is ambigious"


class UnknownFilterError(MoyaError):
    default_message = "no such filter"


class AttributeTypeError(MoyaError):
    """An error caused by an attribute containing the wrong type of data"""
    def __init__(self, element, name, value, type_name):
        self.element = element
        self.name = name
        self.type_name = type_name
        self.value = value
        msg = "%r attribute should be a valid %s (not %r)" % (name,
                                                              type_name,
                                                              value)
        super(AttributeTypeError, self).__init__(msg)


class ContextError(MoyaError):
    pass


class LibraryLoadError(MoyaError):
    """Raised when a lib could not be read"""
    hide_py_traceback = True
    default_message = "Unable to load library '{lib}'"
    message = "Unable to load library '{lib}' - {error}"

    def __init__(self, error, lib=None, py_exception=None, **kwargs):
        long_name = getattr(lib, 'long_name', None)
        if long_name is None:
            lib = "<unknown>"
        else:
            lib = long_name

        self.lib = lib
        self.py_exception = py_exception
        super(LibraryLoadError, self).__init__(error, lib=lib, **kwargs)


class StartupFailedError(MoyaError):
    pass


class SettingsError(StartupFailedError):
    pass


class LoggingSettingsError(StartupFailedError):
    pass


class AppError(MoyaError):
    hide_py_traceback = True
    error_type = "Application Error"


class AmbiguousAppError(AppError):
    default_message = "More than one app installed for lib '{lib_name}', choices are {apps}"

    def __init__(self, lib_name, apps):
        self.lib_name = lib_name
        self.apps = apps
        super(AmbiguousAppError, self).__init__(lib_name=lib_name, apps=textual_list(apps))


class AppRequiredError(AppError):
    default_message = "No application installed for lib '{lib}'"

    def __init__(self, lib):
        super(AppRequiredError, self).__init__(lib=lib)


class AppMissingError(AppError):
    default_message = "A value for application is required"


class UnknownAppError(AppError):
    default_message = "No app in the project referenced by '{app}'"


class MarkupError(Exception):
    """Unable to render markup"""
