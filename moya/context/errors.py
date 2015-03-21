from __future__ import unicode_literals

from ..compat import implements_to_string, text_type


class ContextError(Exception):
    pass


@implements_to_string
class ContextKeyError(KeyError):
    hide_py_traceback = True
    error_type = "Context Error"
    diagnosis = "Check the index you wish to set exists and supports modifying its values."

    def __init__(self, context, index, message=None):
        if message is not None:
            self.index = text_type(index)
            self.message = message
        else:
            frame = ", ".join("'{}'".format(scope.index or ".") for scope in context.current_frame)
            index = text_type(index)
            if text_type(index).startswith('.'):
                self.message = "'{}' not found in context".format(index)
            else:
                self.message = "index '{}' not found in context frame {}".format(index, frame)

            self.index = index

    def __str__(self):
        return self.message


@implements_to_string
class SubstitutionError(ContextError):
    def __init__(self, exp, start, end, original=None):
        self.exp = exp
        self.start = start
        self.end = end
        self.original = original
        if original is not None:
            self.msg = getattr(original, 'msg', text_type(original))
        else:
            self.msg = None

    # @property
    # def diagnosis(self):
    #     return getattr(self.original, 'diagnosis', None)

    def __str__(self):
        if self.msg:
            return 'substitution failed for ${{{}}} ({})'.format(self.exp, self.msg)
        else:
            return 'substitution failed for ${{{}}}'.format(self.exp)

    def __moyaconsole__(self, console):
        if hasattr(self.original, '__moyaconsole__'):
            self.original.__moyaconsole__(console)
