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
        self.diagnosis = diagnosis or """The referenced template doesn't exists in the templates filesystem. Run the following to see what templates are installed:\n\n **$ moya fs templates --tree**"""

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
    def __init__(self, msg, path, lineno, start, end, code=None, raw_path=None, diagnosis=None, original=None, template_stack=None):
        self.msg = msg
        self.path = path
        self.lineno = lineno
        self.start = start
        self.end = end
        self._code = code
        self.raw_path = raw_path
        self.diagnosis = diagnosis
        self.original = original
        self.template_stack = template_stack or []
        self.frames = []
        super(TemplateError, self).__init__()

    def __str__(self):
        return self.msg

    def __repr__(self):
        return 'File "%s", line %s: %s' % (self.path, self.lineno, self.msg)

    def get_moya_error(self):
        return 'File "%s", line %s: %s' % (self.path, self.lineno, self.msg)

    def add_template_frames(self, template_stack):
        from ..trace import Frame
        from .moyatemplates import Node
        for node in self.template_stack:
            print(node)
            node = getattr(node, 'node', node)
            if not isinstance(node, Node):
                continue
            if node.tag_name != 'root':
                frame = Frame(node.code,
                              node.template.path,
                              node.location[0],
                              raw_location=node.template.raw_path,
                              cols=node.location[1:],
                              format="moyatemplate")

                self.frames.append(frame)

    def add_frames(self, frames):
        self.frames.extend(frames)

    def extend_moya_trace(self, context, traceback):
        traceback.stack.append(self.frames)
        # from ..trace import Frame
        # from .moyatemplates import Node
        # base = context.get('.sys.base', '')
        # exc = self

        # def relativefrom(base, path):
        #     if path.startswith(base):
        #         path = "./" + path[len(base):]
        #     return path

        # for node in self.template_stack:
        #     node = getattr(node, 'node', node)
        #     if not isinstance(node, Node):
        #         continue
        #     if node.tag_name != 'root':
        #         frame = Frame(node.code,
        #                       relativefrom(base, node.template.path),
        #                       node.location[0],
        #                       raw_location=node.template.raw_path,
        #                       cols=node.location[1:],
        #                       format="moyatemplate")

        #         traceback.stack.append(frame)

        # frame = Frame(exc._code,
        #               relativefrom(base, exc.path),
        #               exc.lineno,
        #               raw_location=getattr(exc, 'raw_path', None),
        #               cols=(exc.start, exc.end),
        #               format="moyatemplate")
        # traceback.stack.append(frame)


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
    pass

    # def __init__(self, msg, path, lineno, start, end, code=None, original=None, raw_path=None, diagnosis=None):
    #     super(RenderError, self).__init__(msg, path, lineno, start, end, code=code, raw_path=raw_path)
    #     self.original = original
    #     self.diagnosis = diagnosis


# class ExpressionError(RenderError):
#     def __init__(self, msg, node, expression_error):
#         super(ExpressionError, self).__init__(self, msg, node)
#         self.expression_error = expression_error
