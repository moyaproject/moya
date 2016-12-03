from __future__ import unicode_literals
from __future__ import print_function

import os
from . import syntax


class Frame(object):
    def __init__(self,
                 code,
                 location,
                 lineno,
                 path=None,
                 obj=None,
                 cols=None,
                 one_line=False,
                 libid=None,
                 format="xml",
                 raw_location=None):
        self.code = code
        self._location = location
        self.lineno = lineno
        self.obj = obj
        self.cols = cols
        self.one_line = one_line
        self.format = format
        self.libid = libid
        self._raw_location = raw_location

    def __repr__(self):
        return "<frame '{}'>".format(self.location)

    @property
    def location(self):
        location = self._location
        homedir = os.environ.get('HOME', None)
        if homedir and location.startswith(homedir + '/'):
            location = '~/' + location[len(homedir) + 1:]
        if self.obj:
            return 'File "{}", line {}, in {}'.format(location, self.lineno, self.obj)
        else:
            if self.cols:
                return 'File "{}", line {}, col {}'.format(location, self.lineno, self.cols[0])
            else:
                return 'File "{}"'.format(location)

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
            lineno = max(0, self.lineno - 5)

            return syntax.highlight(self.format,
                                    self.code,
                                    lineno,
                                    lineno + 10,
                                    highlight_lines=[self.lineno],
                                    highlight_range=[self.lineno, self.cols[0], self.cols[1]] if self.cols else None)
        except Exception as e:
            raise
            from traceback import print_exc
            print_exc(e)
