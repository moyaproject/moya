# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from .tools import lazystr

import sys
import platform
import warnings
import re
from threading import RLock
from textwrap import wrap, dedent
warnings.filterwarnings("ignore")
from os.path import splitext

try:
    import colorama
except ImportError:
    colorama = None
else:
    colorama.init()


PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3
WIN = sys.platform.startswith('win')

if PY3:
    text_type = str
    binary_type = bytes
    xrange = range
    string_types = (str, bytes)
else:
    text_type = unicode
    binary_type = str
    string_types = (basestring,)


class ConsoleHighlighter(object):

    styles = {}
    highlights = []

    @classmethod
    def highlight(cls, text, default_style=''):
        cls.compile()
        text = AttrText(text)
        default_style = style(default_style or cls.styles.get(None, ''))

        if default_style:
            text.add_span(0, len(text), **default_style)

        for highlight in cls._compiled_highlights:
            for match in highlight.finditer(text):
                for k, v in match.groupdict().items():
                    if k in cls._compiled_styles and v:
                        start, end = match.span(k)
                        text.add_span(start, end, **cls._compiled_styles[k])
        return text

    @classmethod
    def compile(cls):
        if not hasattr(cls, '_compiled_highlights'):
            cls._compiled_highlights = [re.compile(h, re.UNICODE | re.DOTALL | re.MULTILINE) for h in cls.highlights]
            cls._compiled_styles = {k: style(v) for k, v in cls.styles.items()}


class XMLHighlighter(ConsoleHighlighter):
    styles = {
        "xmlns": "italic",
        "tag": "bold blue not dim",
        "attribute": "not bold cyan",
        "string": "yellow",
        "substitution": "bold magenta",
        "templatetag": "bold magenta",
        "braced": "bold",
        "comment": "dim italic not bold"
    }

    highlights = [
        r'(?P<tag>\<[^\!].*?\>)',
        r'(?P<attribute>\s\S*?=\".*?\")',
        r'(?P<string>\".*?\")',
        r'(?P<braced>\{.*?\})',
        r'(?P<substitution>\$\{.*?\})',
        r'(?P<templatetag>\{\%.*?\%\})',
        r'(?P<comment>\<\!\-\-.*?\-\-\>)',
    ]


class TemplateHighlighter(ConsoleHighlighter):
    styles = {
        "tag": "bold blue not dim",
        "attr": "cyan not bold",
        "string": "yellow",
        "substitution": "bold magenta",
        "templatetag": "bold",
        "comment": "dim white italic"
    }

    highlights = [
        r'(?P<templatetag>\{\%.*?\%\})',
        r'(?P<tag>\<.*?\>)',
        r'(?P<attr>\s\S*?=\".*?\")',
        r'(?P<string>\".*?\")',
        r'(?P<substitution>\$\{.*?\})',
        r'(?P<comment>\<\!\-\-.*?\-\-\>)',
    ]


class PythonHighlighter(ConsoleHighlighter):
    styles = {
        "comment": "dim white italic",
        "string": "yellow"
    }
    highlights = [
    ]


class INIHighligher(ConsoleHighlighter):
    styles = {
        "section": "bold green",
        "key": "bold",
        "value": "cyan",
        "substitution": "bold magenta",
        "comment": "dim white italic",
    }
    highlights = [
        r'^(?P<key>\S+?)\s*?\=\s*?(?P<value>.*?)$',
        r'^\s+?(?P<value>.+?)$',
        r'(?P<substitution>\$\{.*?\})',
        r'^(?P<section>\[.*?\])',
        r'^(?P<comment>\#.*?)$'
    ]


def style(style_def):
    """Convert a console style definition in to dictionary

    >>> style("bold red on yellow")
    {fg="red", bg="yellow", bold=True}

    """
    if not style_def:
        return {}
    if isinstance(style_def, dict):
        return style_def
    colors = {"yellow", "magenta", "green", "cyan", "blue", "red", "black", "white"}
    text_styles = {"bold", "underline", "dim", "reverse", "italic"}
    style = {}
    foreground = True
    style_set = True
    for s in style_def.split(' '):
        if s == "on":
            foreground = False
        elif s == "not":
            style_set = False
        elif s in colors:
            style["fg" if foreground else "bg"] = s
        elif s in text_styles:
            style[s] = style_set
        else:
            raise ValueError("unknown style '{}'".format(s))
    return style


class AttrText(text_type):
    """A string with associate console attribute information"""
    def __init__(self, text, spans=None, *args, **kwargs):
        super(AttrText, self).__init__()
        self.attr_spans = spans or []

    def __repr__(self):
        return 'AttrText(%r)' % super(AttrText, self).__repr__()

    def add_span(self, start, end=None, **attrs):
        """Apply attributes to a span in the string"""
        #if end < 0 or start > len(self):
        #    return
        if end is None:
            end = len(self)
        self.attr_spans.append((max(0, start),
                                min(len(self), end),
                                attrs))

    def splitlines(self):
        """Split text in to lines, preserving attributes"""
        bucket_shift = 6
        lines = [[] for _ in xrange((len(self) >> bucket_shift) + 1)]
        pos = 0
        new_lines = []
        line_count = 0
        find = self.find
        l = len(self)
        while pos < l:
            line_end = find('\n', pos)
            if line_end == -1:
                line_end = len(self)  # - 1
            new_lines.append(AttrText(self[pos:line_end]))
            for line_no in xrange(pos >> bucket_shift, (line_end >> bucket_shift) + 1):
                lines[line_no].append((pos, line_end, line_count))
            line_count += 1
            pos = line_end + 1

        for start, end, attrs in self.attr_spans:
            for line_list in lines[start >> bucket_shift:(end >> bucket_shift) + 1]:
                for line_start, line_end, line_offset in line_list:
                    line = new_lines[line_offset]
                    line.attr_spans.append((max(0, start - line_start), min(len(line), end - line_start), attrs))

        return new_lines

    def __moyaconsole__(self, console):
        """Write to a console (called by Console.text)"""
        chars = list(self)
        attrs = [{} for c in chars]
        for start, end, span_attrs in self.attr_spans:
            for r in range(start, end):
                attrs[r].update(span_attrs)

        last_attrs = {}
        accum = []
        text = []
        accum_append = accum.append
        text_append = text.append

        for c, c_attrs in zip(chars, attrs):
            if c_attrs == last_attrs:
                accum_append(c)
            else:
                if accum:
                    span_text = ''.join(accum)
                    text_append((span_text, last_attrs))
                del accum[:]
                accum_append(c)
                last_attrs = c_attrs

        if accum:
            span_text = ''.join(accum)
            text_append((span_text, last_attrs))

        console_out = console.__call__

        with console._lock:
            for text, attrs in text:
                console_out(text, **attrs)

if platform.system() == 'Windows':

    def getTerminalSize():
        try:
            ## {{{ http://code.activestate.com/recipes/440694/ (r3)
            from ctypes import windll, create_string_buffer

            # stdin handle is -10
            # stdout handle is -11from
            # stderr handle is -12

            h = windll.kernel32.GetStdHandle(-12)
            csbi = create_string_buffer(22)
            res = windll.kernel32.GetConsoleScreenBufferInfo(h, csbi)

            if res:
                import struct
                (bufx, bufy, curx, cury, wattr,
                 left, top, right, bottom, maxx, maxy) = struct.unpack(b"hhhhHhhhhhh", csbi.raw)
                sizex = right - left + 1
                sizey = bottom - top + 1
            else:
                sizex, sizey = 80, 25  # can't determine actual size - return default values
            return sizex, sizey
        except:
            return 80, 25

else:

    def getTerminalSize():
        def ioctl_GWINSZ(fd):
            try:
                import fcntl
                import termios
                import struct
                import os
                cr = struct.unpack('hh', fcntl.ioctl(fd, termios.TIOCGWINSZ, '1234'))
            except:
                return None
            return cr
        cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)
        if not cr:
            import os
            try:
                fd = os.open(os.ctermid(), os.O_RDONLY)
                cr = ioctl_GWINSZ(fd)
                os.close(fd)
            except:
                pass
        if cr:
            return int(cr[1]), int(cr[0])
        try:
            h, w = os.popen("stty size", "r").read().split()
            return int(w), int(h)
        except:
            pass
        return 80, 25


class Cell(object):
    """A table cell"""

    def __init__(self, text, processor=None, **attribs):
        self.text = text_type(text)
        self.processor = processor or (lambda t: t)
        self.attribs = attribs

    @classmethod
    def create(cls, cell, processor=None):
        if isinstance(cell, Cell):
            return cell
        if cell is None:
            return Cell('None', italic=True, dim=True)
        try:
            text = text_type(cell)
        except:
            text = repr(cell)
        attribs = {}
        return Cell(text, processor=processor, **attribs)

    def __len__(self):
        return 2

    def __iter__(self):
        yield self.processor(self.text)
        yield self.attribs

    def __getitem__(self, index):
        if index == 0:
            return self.processor(self.text)
        if index == 1:
            return self.attribs
        raise IndexError(index)

    def __repr__(self):
        return 'Cell(%r)' % self.text

    def get_min_length(self):
        try:
            return min(max(len(token) for token in self.text.split(splitter))
                       for splitter in (' ', ',', '/'))
        except ValueError:
            return 1

    def get_lines(self, max_length=80, continuation='↪'):
        center = self.attribs.get("center", False)
        if max_length is None:
            return self.text.splitlines()
        lines = []
        if max_length < 8:
            continuation = ''

        def add_line(line):
            if not line:
                lines.append('')
                return
            new_lines = []
            while len(line) > max_length:
                broken_line = line[:max_length]
                break_pos = max_length
                for break_char in ' /.-_':
                    if break_char in broken_line[8:]:
                        break_pos = broken_line.rindex(break_char)
                        break
                new_line = line[:break_pos]
                remaining_line = continuation + line[break_pos:]
                new_lines.append(new_line)
                line = remaining_line
            if line:
                new_lines.append(line)
            if center:
                new_lines = [l.center(max_length) for l in new_lines]
            lines.extend(new_lines)

        for line in self.text.splitlines():
            tokens = line.split(' ')[::-1]
            line_tokens = []

            while tokens:
                token = tokens.pop()
                line_tokens.append(token)
                new_line = " ".join(line_tokens)
                if len(new_line) > max_length:
                    if len(line_tokens) > 1:
                        line_tokens.pop()
                        add_line(" ".join(line_tokens))
                        del line_tokens[:]
                        tokens.append(token)
                    else:
                        add_line(new_line)
                        del line_tokens[:]

            if line_tokens:
                add_line(" ".join(line_tokens))

        return lines

    def expand(self, max_length=None, continuation='↪'):
        lines = self.get_lines(max_length=max_length, continuation=continuation)
        expanded_lines = [Cell(line, processor=self.processor, **self.attribs) for line in lines]
        return expanded_lines


def make_table_header(*headers):
    """Create the first row of headers in a table."""
    return [[Cell(h, bold=True) for h in headers]]


class _TextOut(object):
    def __init__(self):
        self.text = []

    def write(self, text):
        if not isinstance(text, text_type):
            text = text_type(text, 'utf-8')
        self.text.append(text)

    def flush(self):
        pass

    def getvalue(self):
        return ''.join(self.text)


class _ConsoleFileInterface(object):
    """A simple writable file-like proxy."""

    def __init__(self, console, **style):
        self._console = console
        self._style = style

    def write(self, text):
        self._console(text, **self._style)


class Console(object):
    """Write output to the console, with styles and color."""

    fg_colors = dict(black=30,
                     red=31,
                     green=32,
                     yellow=33,
                     blue=34,
                     magenta=35,
                     cyan=36,
                     white=37)

    bg_colors = dict(black=40,
                     red=41,
                     green=42,
                     yellow=43,
                     blue=44,
                     magenta=45,
                     cyan=46,
                     white=47)

    _lock = RLock()

    def __init__(self, out=None, nocolors=False, text=False, width=None, html=False, unicode_borders=True):
        self.unicode_borders = unicode_borders
        if html:
            self.html = True
            self.encoding = 'utf-8'
            self.out = _TextOut()
            self.terminal_width = width or 120
            return
        if text:
            self.unicode_borders = False
            nocolors = True
            out = _TextOut()
        self.out = out or sys.stdout
        self.html = html

        self.encoding = getattr(self.out, 'encoding', 'utf-8') or 'utf-8'
        if nocolors:
            self.terminal_colors = False
        else:
            self.terminal_colors = self.is_terminal()
            if sys.platform.startswith('win') and not colorama:
                self.terminal_colors = False
        if self.is_terminal():
            w, h = getTerminalSize()
            self.terminal_width = w
        else:
            self.terminal_width = width or 80
        self.unicode_borders = self.terminal_colors and not WIN
        if not self.terminal_width:
            self.terminal_width = 80

    @property
    def width(self):
        return self.terminal_width

    def make_file_interface(self, **style):
        return _ConsoleFileInterface(self)

    def flush(self):
        with self._lock:
            if hasattr(self.out, 'flush'):
                self.out.flush()

    def update_terminal_width(self):
        with self._lock:
            if self.is_terminal():
                w, h = getTerminalSize()
                self.terminal_width = w or 80

    def get_text(self):
        assert isinstance(self.out, _TextOut)
        return self.out.getvalue()

    def __repr__(self):
        return "<console>"

    def is_terminal(self):
        try:
            return self.out.isatty() and not self.html
        except AttributeError:
            return False

    def _html_out(self,
                  text,
                  fg=None,
                  bg=None,
                  bold=False,
                  underline=False,
                  dim=False,
                  reverse=False,
                  italic=False,
                  nl=False):
        css_classes = []
        append = css_classes.append
        if bold:
            append('console-bold')
        if underline:
            append('console-underline')
        if dim:
            append('console-dim')
        if reverse:
            append('console-reverse')
        if italic:
            append('console-italic')
        if fg is not None:
            append('console-foreground-' + fg)
        if bg is not None:
            append('console-background-' + bg)
        if italic:
            append('console-italic')

        class_attrib = " ".join(css_classes)

        if class_attrib:
            tag = '<span class="{}">'.format(class_attrib)
            self.out.write(tag)

        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        text = text.replace('\n', '<br>')
        self.out.write(text.encode('utf-8'))

        if class_attrib:
            self.out.write('</span>')

        if nl:
            self.out.write('<br>')

        return self

    def __call__(self,
                 text,
                 fg=None,
                 bg=None,
                 bold=False,
                 underline=False,
                 dim=False,
                 reverse=False,
                 italic=False,
                 nl=False,
                 asstr=False,
                 center=False):
        if isinstance(text, AttrText):
            return self.text(text)
        if self.html:
            return self._html_out(text,
                                  fg=fg,
                                  bg=bg,
                                  bold=bold,
                                  underline=underline,
                                  dim=dim,
                                  reverse=reverse,
                                  italic=italic,
                                  nl=nl)
        if isinstance(text, lazystr):
            text = text_type(text)
        if isinstance(text, bytes):
            text = text.decode('ascii', 'replace')
        if PY2:
            text = text.encode(self.encoding, 'replace')

        if nl:
            text += '\n'
        if not self.terminal_colors:
            if asstr:
                return text
            self.out.write(text)
            return self
        out = []
        fg = self.fg_colors.get(fg, None) if fg is not None else None
        bg = self.bg_colors.get(bg, None) if bg is not None else None
        attrs = []
        if bold:
            attrs.append(1)
        if dim:
            attrs.append(2)
        if italic:
            attrs.append(3)
        if underline:
            attrs.append(4)
        if reverse:
            attrs.append(7)

        attrs.append(fg)
        attrs.append(bg)

        display_attributes = ["%i" % da for da in attrs if da is not None]

        if display_attributes:
            out.append('\x1b[%sm' % ';'.join(display_attributes))
        out.append(text)
        if display_attributes:
            out.append("\x1b[0m")
        if asstr:
            return ''.join(out)

        if PY3:
            def console_encode(s):
                """Work around a bug with colorama on Windows"""
                if self.encoding.lower() != 'utf-8':
                    return s.encode(self.encoding, 'replace').decode(self.encoding)
                return s
            with self._lock:
                self.out.write(''.join(
                               (text.decode('utf-8', 'replace') if isinstance(text, bytes) else console_encode(text))
                               for text in out))
        else:
            with self._lock:
                self.out.write(b''.join(
                               (text.encode(self.encoding, 'replace') if isinstance(text, text_type) else text)
                               for text in out))
        return self

    def progress(self, msg, num_steps=100, width=12):
        """A context manager to manage progress bars"""
        from .progress import Progress, ProgressContext
        p = Progress(self, msg, num_steps=num_steps, width=width)
        p.render()
        return ProgressContext(p)

    def nl(self, count=1):
        with self._lock:
            if self.html:
                self.out.write('<br>' * count)
            else:
                self.out.write('\n' * count)
        return self

    def div(self, msg=None, **attrs):
        """Inserts a horizontal dividing line"""
        if 'italic' not in attrs:
            attrs['italic'] = True
        with self._lock:
            self.update_terminal_width()
            if msg is None:
                self("-" * self.terminal_width, dim=True).nl()
            else:
                space = self.terminal_width - len(msg)
                lspace = space // 2
                rspace = space - lspace
                self('-' * lspace, dim=True)(msg, **attrs)('-' * rspace, dim=True).nl()

        return self

    def text(self, text, **params):
        with self._lock:
            if isinstance(text, AttrText):
                text.__moyaconsole__(self)
            else:
                self(text, **params).nl()
        return self

    def wraptext(self, text, do_dedent=True, **attribs):
        """Output wrapper text"""
        with self._lock:
            if do_dedent:
                text = dedent(text)
            for line in text.splitlines():
                wrapped_text = wrap(line, self.terminal_width)
                self.text("\n".join(wrapped_text).lstrip(), **attribs)
        return self

    def xmlsnippet(self, code, lineno=1, colno=None, extralines=3, line_numbers=True):
        """Render a snippet of xml, with a highlighted line"""
        with self._lock:
            if not code:
                return
            if colno is not None:
                highlight_columns = (colno - 1, colno)
            else:
                highlight_columns = None
            _lineno = max(0, lineno - extralines)

            self.snippet(code,
                         (_lineno, _lineno + extralines * 2 + 1),
                         highlight_line=lineno,
                         highlight_columns=highlight_columns,
                         line_numbers=True)
        return self

    def pysnippet(self, code, lineno=1, colno=None, extralines=3, line_numbers=True):
        """Render a snippet of xml, with a highlighted line"""
        with self._lock:
            if not code:
                return
            if colno is not None:
                highlight_columns = (colno - 1, colno)
            else:
                highlight_columns = None
            _lineno = max(0, lineno - extralines)

            highlighter = PythonHighlighter()

            self.snippet(code,
                         (_lineno, _lineno + extralines * 2 + 1),
                         highlight_line=lineno,
                         highlight_columns=highlight_columns,
                         line_numbers=True,
                         highlighter=highlighter)
        return self

    def ini(self, code):
        highlighter = INIHighligher()
        self.snippet(code,
                     highlighter=highlighter,
                     line_numbers=False)

    def templatesnippet(self, code, lineno=1, colno=None, endcolno=None, extralines=3, line_numbers=True):
        with self._lock:
            if not code:
                return
            if colno is not None:
                highlight_columns = (colno - 1, colno if endcolno is None else endcolno)
            else:
                highlight_columns = None
            _lineno = max(0, lineno - extralines)
            self.snippet(code,
                         (_lineno, _lineno + extralines * 2 + 1),
                         highlight_line=lineno,
                         highlight_columns=highlight_columns,
                         highlighter=TemplateHighlighter,
                         line_numbers=line_numbers)
        return self

    def xml(self, code):
        code = code.strip('\n') + '\n'
        self.snippet(code, line_numbers=False)
        return self
        # with self._lock:
        #     self.update_terminal_width()
        #     if not self.terminal_colors:
        #         self(code).nl()
        #     else:
        #         try:
        #             from pygments import highlight
        #             from pygments.lexers import XmlLexer
        #             from pygments.formatters import TerminalFormatter
        #         except ImportError:
        #             self(xml).nl()
        #         else:
        #             hcode = highlight(code, XmlLexer(), TerminalFormatter())
        #             self(hcode)
        #     return self

    def document_error(self, msg, path, code, lineno, colno, diagnosis=None):
        with self._lock:
            self.div()
            if colno is None:
                self('File "%s", line %i' % (path, lineno)).nl()
            else:
                self('File "%s", line %i, column %i' % (path, lineno, colno)).nl()
            self(msg, fg="red", bold=True).nl()
            if diagnosis:
                self.table([[Cell(diagnosis, italic=True)]])
            self.xmlsnippet(code, lineno, colno)

        return self

    def success(self, msg):
        with self._lock:
            self.wraptext(msg, fg="green", bold=True)
        return self

    def error(self, msg):
        """Renders a generic error"""
        with self._lock:
            self.wraptext(msg, fg="red", bold=True)
        return self

    def exception(self, exc, tb=False):
        with self._lock:
            self.update_terminal_width()

            if not tb:
                if hasattr(exc, 'get_moya_error'):
                    exc_text = exc.get_moya_error()
                else:
                    exc_text = text_type(exc)
                self(exc_text, fg="red", bold=True).nl()
                return self

            if isinstance(exc, string_types):
                raw_tb = exc
            else:
                import traceback
                raw_tb = traceback.format_exc()

            if self.terminal_colors:
                from pygments import highlight
                from pygments.lexers import PythonTracebackLexer, Python3TracebackLexer
                from pygments.formatters import TerminalFormatter

                if PY2:
                    lexer = PythonTracebackLexer
                else:
                    lexer = Python3TracebackLexer

                htb = highlight(raw_tb,
                                lexer(),
                                TerminalFormatter())
                self(htb)
            else:
                self(raw_tb)

        return self

    def table(self,
              table,
              header_row=None,
              grid=True,
              header=True,
              divider_attribs=None,
              pad=1,
              border_style=0,
              dividers=True,
              cell_processors=None):
        """Renders a table of cells with an optional ASCII grid

        A table should be a list of lists, where each element is either a string
        or a tuple of a string and a dictionary of attributes.

        """
        table = list(table)
        with self._lock:
            if cell_processors is None:
                cell_processors = {}
            if header_row is not None and header:
                table = make_table_header(*header_row) + table[:]
            tl = tr = bl = br = ir = it = il = ib = ii = '+'
            hor = '-'
            ver = '|'
            continuation = '...'
            if self.unicode_borders:
                continuation = '↪  '
                if border_style == 0:
                    tl = '╭'
                    tr = '╮'
                    bl = '╰'
                    br = '╯'
                    il = '├'
                    ir = '┤'
                    it = '┬'
                    ib = '┴'
                    hor = '─'
                    ver = '│'
                    ii = '┼'
                elif border_style == 1:
                    tl = '╔'
                    tr = '╗'
                    bl = '╚'
                    br = '╝'
                    il = '╠'
                    ir = '╣'
                    it = '╦'
                    ib = '╩'
                    hor = '═'
                    ver = '║'
                    ii = '╬'
                elif border_style == 2:
                    tl = '┏'
                    tr = '┓'
                    bl = '┗'
                    br = '┛'
                    il = '┣'
                    ir = '┫'
                    it = '┳'
                    ib = '┻'
                    hor = '━'
                    ver = '┃'
                    ii = '╋'

            self.update_terminal_width()
            terminal_width = self.terminal_width
            if WIN:
                terminal_width -= 1
            table = [[Cell.create(cell, cell_processors.get(rowno))
                      for rowno, cell in enumerate(row)] for row in table]

            def cell_len(cell):
                try:
                    return max(len(line) for line in cell.get_lines(max_length=terminal_width))
                except ValueError:
                    return 0

            cell_lengths = []
            cell_min_lengths = []
            for row_no in xrange(len(table[0])):
                cell_lengths.append(max(cell_len(col[row_no]) for col in table))
                cell_min_lengths.append(max(col[row_no].get_min_length() for col in table))

            num_cols = len(cell_lengths)
            table_padding = (num_cols * pad * 2) + (num_cols - 1) + grid * 2
            table_width = sum(cell_lengths) + table_padding
            if table_width > self.terminal_width:

                # make each column its minimum until the table fits, starting with the widest column
                for i, (cell_length, min_length) in sorted(enumerate(zip(cell_lengths, cell_min_lengths)), key=lambda c: c[1][1], reverse=True):
                    over_size = table_width - terminal_width
                    cell_lengths[i] -= min(over_size, (cell_length - min_length))
                    table_width = sum(cell_lengths) + table_padding
                    if sum(cell_lengths) <= terminal_width:
                        break

                over_space = table_width - terminal_width
                while over_space > 0:
                    largest_value = 0
                    largest_index = None
                    for i, l in enumerate(cell_lengths):
                        if l > largest_value:
                            largest_value = l
                            largest_index = i
                    if largest_index is None:
                        break
                    reduce = min(over_space, int(largest_value - 4))
                    cell_lengths[largest_index] -= reduce
                    if reduce <= 0:
                        break
                    over_space -= reduce

            if grid:
                if divider_attribs is None:
                    divider_attribs = {"dim": True}
                top_divider = (tl + '%s' + tr) % it.join(hor * (l + pad * 2) for l in cell_lengths)
                mid_divider = (il + '%s' + ir) % ii.join(hor * (l + pad * 2) for l in cell_lengths)
                bot_divider = (bl + '%s' + br) % ib.join(hor * (l + pad * 2) for l in cell_lengths)
            else:
                divider_attribs = {}
                divider = ''
                top_divider = ''
                mid_divider = ''
                bot_divider = ''

            if grid:
                self(top_divider, **divider_attribs).nl()

            padding = pad * ' '
            separator = ver if grid else ' '
            for row_no, row in enumerate(table):
                if row_no == len(table) - 1:
                    divider = bot_divider
                else:
                    divider = mid_divider
                expanded_cells = [cell.expand(cell_length, continuation=continuation)
                                  for cell_length, cell in zip(cell_lengths, row)]
                max_height = max(len(cell) for cell in expanded_cells)

                for cell_line_no in xrange(max_height):
                    expanded_row = [ecell[cell_line_no] if cell_line_no < len(ecell) else Cell('')
                                    for ecell in expanded_cells]
                    if grid:
                        r = [(ver, divider_attribs)]
                    else:
                        r = []
                    append = r.append

                    last_i = len(expanded_row) - 1
                    for i, (cell, cell_length) in enumerate(zip(expanded_row, cell_lengths)):
                        text, attribs = cell
                        if grid:
                            cell_text = (padding + text.ljust(cell_length) + padding)
                        else:
                            cell_text = (padding * (i > 0) + text.ljust(cell_length) + padding * (i < last_i))
                        cell_text = cell.processor(cell_text)
                        append((cell_text, attribs))
                        if grid or i < last_i:
                            append((separator, divider_attribs))

                    for text, attribs in r:
                        self(text, **attribs)
                    self.nl()

                if grid:
                    if dividers and not header:
                        self(divider, **divider_attribs).nl()
                    elif not dividers:
                        if row_no == len(table) - 1:
                            self(divider, **divider_attribs).nl()
                    elif row_no in (0, len(table) - 1):
                        self(divider, **divider_attribs).nl()
            return self

    def cat(self, contents, path):
        with self._lock:
            self.update_terminal_width()
            if not self.terminal_colors:
                self(contents).nl()
            else:

                ext = splitext(path)[-1].lower()
                if ext in ('.htm', '.html', '.text'):
                    self(TemplateHighlighter.highlight(contents))
                    return self
                elif ext in ('.xml',):
                    self(XMLHighlighter.highlight(contents))
                    return self

                from pygments import highlight
                from pygments.formatters import TerminalFormatter
                from pygments.lexers import get_lexer_for_filename, guess_lexer
                from pygments.util import ClassNotFound
                try:
                    lexer = guess_lexer(contents)
                except ClassNotFound:
                    try:
                        lexer = get_lexer_for_filename(path)
                    except ClassNotFound:
                        lexer = None

                if lexer is None:
                    self(contents).nl()
                else:
                    hcode = highlight(contents, lexer, TerminalFormatter())
                    self(hcode)
            return self

    def snippet(self, xml, line_range=None, line_numbers=True, highlight_line=None, highlight_columns=None, highlighter=None):
        if isinstance(xml, binary_type):
            xml = xml.decode('utf-8', 'replace')
        with self._lock:
            self.update_terminal_width()
            if line_range is None:
                start = 1
                end = None
            else:
                start, end = line_range

            #xml = xml.replace('\r', '\n')
            xml = AttrText(xml)

            if highlighter is None:
                highlighter = XMLHighlighter

            xml = highlighter.highlight(xml)

            lines = xml.splitlines()

            if end is None:
                end = len(lines) + 1
            if start < 1:
                start = 1
            if end > len(lines):
                end = len(lines) + 1
            lines = lines[start - 1:end - 1]

            try:
                max_number_length = max(len(text_type(n + 1)) for n in range(start, end)) + 1
            except:
                max_number_length = 0
            if max_number_length < 6:
                max_number_length = 6

            if line_numbers:
                for i, line in enumerate(lines):
                    line_no = i + start
                    if highlight_line is not None and highlight_line == line_no:
                        if self.terminal_colors:
                            if self.unicode_borders:
                                indicator = "\u2022"
                            else:
                                indicator = "*"
                        else:
                            indicator = "*"
                        number = (indicator + text_type(line_no)).rjust(max_number_length, ' ') + ' '

                        if highlight_columns:
                            col_start, col_end = highlight_columns
                            line.add_span(col_start, col_end, fg="red", underline=True)

                        self(number, fg="blue", bold=True)(line).nl()
                    else:
                        number = text_type(line_no).rjust(max_number_length) + ' '
                        self(number, fg="blue", dim=False)(line).nl()
            else:
                for line in lines:
                    self(line).nl()
        return self

    def obj(self, context, obj, **kwargs):
        """Writes information regarding an object to the console"""
        with self._lock:
            if hasattr(obj, '__moyaconsole__'):
                try:
                    obj.__moyaconsole__(self)
                except Exception:
                    pass
                else:
                    return self

            if isinstance(obj, string_types):
                self.text(context.to_expr(obj, max_size=1000), **kwargs)
            elif isinstance(obj, dict):
                table = []
                for k, v in obj.items():
                    table.append([k, context.to_expr(v, max_size=1000)])
                self.table(table, header_row=["key", "value"])
            elif isinstance(obj, (list, tuple)):
                table = [(i, context.to_expr(v, max_size=1000)) for i, v in enumerate(obj)]
                self.table(table, header_row=["index", "value"])
            elif isinstance(obj, bool):
                if obj:
                    self.text("True", bold=True, fg="green")
                else:
                    self.text("False", bold=True, fg="red")
            else:
                self.text(context.to_expr(obj, max_size=1000), **kwargs)
            return self

    def show_cursor(self, show=True):
        if not WIN:
            if show:
                self.out.write("\033[?25h")
            else:
                self.out.write("\033[?25l")
        self.out.flush()


def test_table(console):
    long_text = """If you are writing an application of any size, it will most likely require a number of files to run - files which could be stored in a variety of possible locations. Furthermore, you will probably want to be able to change the location of those files when debugging and testing. You may even want to store those files somewhere other than the user's hard drive."""

    bold = dict(bold=True)
    red = dict(fg="red")

    table = [
             [("foo", dict(reverse=True, bold=True, dim=True)), ("100", red), "Some text"],
             [("long text!", dict(reverse=True, bold=True, dim=True)), long_text, "Some text"],
             [("bar", bold), ("120", red), ("Some more text\nline 2\nline 3", {'bg':'green'})],
             [("foo", bold), ("100", red), "Some text"],
             [("bar", bold), ("120", red), "Some more text"],
             [("A longer cell...\nwith multiple lines", bold), (120344, red), "Some more text"],
             [("foo", bold), ("100", red), "Some text"],
             [("bar", bold), ("120", red), "Some more text"],
            ]
    console.table(table, grid=True)
    console.nl()


if __name__ == "__main__":

    console = Console()
    test_table(console)

    import sys
    #sys.exit()

    xml = """<moya xmlns="http://moyaproject.com">
    <mountpoint name="main">
        <url url="{*path}">
            <call py="static.check_hide" dst="hidden" >
                <set value="url.path" />
            </call>
            <if test="url.path $= '/'">
                <call py="static.get_dirlist" dst="dirlist">
                    <set value=".fs[app.settings.fs]" />
                    <set value="url.path" />
                </call>
                <servepage template="dirlist.html" withscope="y" if="dirlist" />
            </if>
            <else>
                <serve fs="${app.settings.fs}" path="${url.path}" />
            </else>
        </url>
    </mountpoint>
</moya>
<!-- Commented <b>out</b> -->
"""
    console = Console()
    #console.xml_trace(xml, (4, 11), highlight_line=8)
    console.snippet(xml, (4, 11), highlight_line=7, highlight_columns=(12,100))

if 0:
    console = Console()
    console('Hello ', dim=True)("World!", bold=True).nl()
    console("Green!", bg="green", fg="white").nl()

    xml = """<moya xmlns="http://moyaproject.com">

<mountpoint name="testmount" libname="root">
    <url name="article" url="/{year}/{month}/{day}/{slug}/" methods="GET" target="viewpost">
        <debug>url main: ${url.year}, ${url.month}, ${url.day}, ${url.slug}</debug>
    </url>
    <url name="front" url="/" methods="GET">
        <debug>Front...</debug>
        <return><str>Front</str></return>
    </url>
</mountpoint>

<macro docname="viewpost">
    <debugIn viewpost</debug>
    <return><str>Hello, World</str></return>
    <return>
        <response template="birthday.html">
            <str dst="title">My Birthday</str>
            <str dst="body">It was my birthday today!</str>
        </response>
    </return>
</macro>

<!--
<macro libname="showapp">
    <debug>App is ${app}</debug>
</macro>

<macro libname="blogmacro">
    <debug>Called blogmacro in blog lib</debug>
</macro>

<macro libname="blogmacro2">
    <debug>Called blogmacro2 with app: ${debug:app}</debug>
</macro>
-->

</moya>"""*10

    console.xmlsnippet(xml, 6)

    try:
        1 / 0
    except Exception as e:
        console.exception(e, tb=True)

    bold = dict(bold=True)
    red = dict(fg="red")

    long_text = """If you are writing an application of any size, it will most likely require a number of files to run - files which could be stored in a variety of possible locations. Furthermore, you will probably want to be able to change the location of those files when debugging and testing. You may even want to store those files somewhere other than the user's hard drive."""

    table = [
             [("foo", dict(reverse=True, bold=True, dim=True)), ("100", red), "Some text"],
             [("long text!", dict(reverse=True, bold=True, dim=True)), long_text, "Some text"],
             [("bar", bold), ("120", red), ("Some more text\nline 2\nline 3", {'bg':'green'})],
             [("foo", bold), ("100", red), "Some text"],
             [("bar", bold), ("120", red), "Some more text"],
             [("A longer cell...\nwith multiple lines", bold), (120344, red), "Some more text"],
             [("foo", bold), ("100", red), "Some text"],
             [("bar", bold), ("120", red), "Some more text"],
            ]
    console.table(table, grid=True)
    console.nl()
    console.table(table, grid=True, header=True)
    console.nl()
    console.table(table, grid=False, pad=0)

    #for line in Cell("""If you are writing an application of any size, it will most likely require a number of files to run - files which could be stored in a variety of possible locations. Furthermore, you will probably want to be able to change the location of those files when debugging and testing. You may even want to store those files somewhere other than the user's hard drive.""").get_lines():
    #        print line
