from __future__ import unicode_literals
from ..compat import implements_to_string, text_type


class MoyaRuntimeError(Exception):
    def __init__(self):
        pass


@implements_to_string
class MissingTemplateError(Exception):
    hide_py_traceback = True
    error_type = "Missing Template Error"

    def __init__(self, path, diagnosis=None):
        self.path = path
        self.diagnosis = diagnosis or """The referenced template doesn't exists in the templates filesystem. Run the following to see what templates are installed:\n\n **$ moya fs template --tree**"""

    def __str__(self):
        return 'Missing template "{}"'.format(self.path)

    __repr__ = __str__


@implements_to_string
class BadTemplateError(MissingTemplateError):

    def __str__(self):
        return 'Unable to load template "%s"' % self.path


@implements_to_string
class RecursiveTemplateError(Exception):
    def __init__(self, path):
        self.path = path

    def __str__(self):
        return "Template '{}' has already been used in an extends directive".format(self.path)


@implements_to_string
class TemplateError(Exception):
    def __init__(self, msg, path, lineno, start, end, code=None, raw_path=None, diagnosis=None):
        self.msg = msg
        self.path = path
        self.lineno = lineno
        self.start = start
        self.end = end
        self.code = code
        self.raw_path = raw_path
        self.diagnosis = diagnosis
        super(TemplateError, self).__init__()

    def __str__(self):
        return self.msg

    def __repr__(self):
        return 'File "%s", line %s: %s' % (self.path, self.lineno, self.msg)

    def get_moya_error(self):
        return 'File "%s", line %s: %s' % (self.path, self.lineno, self.msg)


class TokenizeError(TemplateError):
    """Errors detected when tokenizing templates"""
    pass


class UnmatchedCommentError(TemplateError):
    """Begin comments don't manage end comments"""
    pass


class ParseError(TemplateError):
    pass


class UnknownTagError(ParseError):
    pass


class UnmatchedTagError(ParseError):
    pass


class TagSyntaxError(ParseError):
    pass


class RecursiveExtendsError(ParseError):
    pass


@implements_to_string
class TagError(Exception):
    def __init__(self, msg, node, diagnosis=None):
        self.msg = msg
        self.node = node
        self.diagnosis = diagnosis
        super(TagError, self).__init__("{} {}".format(msg, text_type(node)))

    def __str__(self):
        return self.msg


class RenderError(TemplateError):
    def __init__(self, msg, path, lineno, start, end, code=None, original=None, raw_path=None, diagnosis=None):
        super(RenderError, self).__init__(msg, path, lineno, start, end, code=code, raw_path=raw_path)
        self.original = original
        self.diagnosis = diagnosis


# class ExpressionError(RenderError):
#     def __init__(self, msg, node, expression_error):
#         super(ExpressionError, self).__init__(self, msg, node)
#         self.expression_error = expression_error
