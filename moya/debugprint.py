import inspect
import sys
import os


class DebugPrint(object):
    def __init__(self, f):
        self.f = f

    def write(self, text):
        frame = inspect.currentframe()
        filename = frame.f_back.f_code.co_filename.rsplit(os.sep, 1)[-1]
        lineno = frame.f_back.f_lineno
        prefix = "[%s:%s] " % (filename, lineno)
        if text == os.linesep:
            self.f.write(text)
        else:
            self.f.write(prefix + text)

if not isinstance(sys.stdout, DebugPrint):
    sys.stdout = DebugPrint(sys.stdout)
