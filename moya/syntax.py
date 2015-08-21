from __future__ import unicode_literals
from __future__ import print_function

import re

from .tools import timer, remove_padding
from .compat import iteritems, with_metaclass
from .filter import MoyaFilterBase
from .render import HTML
from .compat import text_type

from textwrap import dedent


def _escape_html(text):
    """Escape text for inclusion in html"""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace(' ', '&nbsp;')


def tabs_to_spaces(line, tab_size=4):
    """Converts tabs to a fixed numbers of spaces at the beginning of a string"""
    spaces = 0
    for c in line:
        if c not in ' \t':
            break
        if c == '\t':
            spaces += tab_size - (spaces % tab_size)
        else:
            spaces += 1
    return ' ' * spaces + line.lstrip()


def highlight(format,
              code,
              start_line=1,
              end_line=None,
              line_numbers=True,
              highlight_lines=None,
              highlight_range=None,
              highlight_range_style="error"):
    if isinstance(code, bytes):
        code = code.decode('utf-8', 'replace')

    HL = HighlighterMeta.highlighters.get(format, Highlighter)
    h = HL()
    html = h.highlight(code,
                       start_line,
                       end_line,
                       line_numbers=line_numbers,
                       highlight_lines=highlight_lines,
                       highlight_range=highlight_range,
                       highlight_range_style=highlight_range_style)
    return html


class HighlighterMeta(type):
    highlighters = {}

    def __new__(cls, name, base, attrs):
        new_class = type.__new__(cls, name, base, attrs)
        format = getattr(new_class, 'format', None)
        if format:
            cls.highlighters[format] = new_class
        flags = re.UNICODE | re.MULTILINE | re.DOTALL
        new_class._compiled_styles = [re.compile(s, flags) for s in new_class.styles]
        return new_class


class HighlighterType(object):
    """Somewhat naive syntax highlighter"""
    line_anchors = True

    styles = []
    _compiled_styles = None

    _re_linebreaks = re.compile(r'$', flags=re.UNICODE | re.MULTILINE | re.DOTALL)

    _highlight_range_padding = 50

    def highlight(self,
                  code,
                  start_line=None,
                  end_line=None,
                  line_numbers=True,
                  highlight_lines=None,
                  highlight_range=None,
                  highlight_range_style="error"):
        if start_line is None:
            start_line = 1

        offset_line = 0

        start_line = max(1, start_line)
        lines = code.splitlines()
        if end_line is None:
            end_line = len(lines)
        lines = ([''] * offset_line) + lines[offset_line:end_line + self._highlight_range_padding + 1]
        code = '\n'.join(tabs_to_spaces(l.rstrip()) for l in lines)

        points = []
        line_starts = [-1]
        add_point = points.append

        for style_regex in self._compiled_styles:
            for match in style_regex.finditer(code):
                for k, v in iteritems(match.groupdict()):
                    if v:
                        start, end = match.span(k)
                        add_point((start, True, k))
                        add_point((end, False, k))

        def sub_linebreaks(match):
            start = match.start(0)
            line_starts.append(start)
            add_point((start, True, ''))
        self._re_linebreaks.sub(sub_linebreaks, code)

        if highlight_range:
            line_no, start, end = highlight_range
            try:
                line_start = line_starts[line_no - 1]
            except IndexError:
                pass
            else:
                hi_start = line_start + start
                hi_end = line_start + end + 1
                add_point((hi_start, True, highlight_range_style))
                add_point((hi_end, False, highlight_range_style))

        points.sort()
        lines_out = []
        hiline = []
        hiline_append = hiline.append
        style_set = set()
        pos = 0

        points = points[::-1]

        while points:
            start_pos, add_style, style = points.pop()
            new_style_set = style_set.copy()

            if style:
                if add_style:
                    new_style_set.add(style)
                else:
                    new_style_set.discard(style)
                while points:
                    peek_start, peek_add, peek_style = points[-1]
                    if peek_style and peek_start == start_pos:
                        if peek_add:
                            new_style_set.add(peek_style)
                        else:
                            new_style_set.discard(peek_style)
                        points.pop()
                    else:
                        break

            if start_pos > pos:
                hiline_append(_escape_html(code[pos:start_pos]))
            pos = start_pos

            if not style:
                if style_set:
                    hiline.append('</span>')
                lines_out.append(hiline[:])
                del hiline[:]
                if new_style_set:
                    hiline_append('<span class="%s">' % ' '.join(new_style_set))
                style_set = new_style_set
                continue

            if new_style_set != style_set:
                hiline_append('</span>')
                if new_style_set:
                    hiline_append('<span class="%s">' % ' '.join(new_style_set))

            style_set = new_style_set

        if hiline:
            lines_out.append(hiline[:])
            lines_out.append('</span>')

        if end_line is None:
            lines_out = lines_out[start_line - 1:]
        else:
            lines_out = lines_out[start_line - 1:end_line]

        def make_line(l):
            text = ''.join(l)
            if text.strip():
                return text.replace('\n', '')
            else:
                return '\n'
        html_lines = [make_line(line) for line in lines_out]

        if line_numbers:
            html_lines = ['<span class="lineno">{0}</span>{1}'.format(line_no, line)
                          for line_no, line in enumerate(html_lines, (start_line or 0))]

        if highlight_lines is None:
            highlight_lines = ()
        if self.line_anchors:
            linet = '<a name="line{1}"></a><div class="line{0} line-{1}">{2}</div>'
        else:
            linet = '<div class="line{0} line-{1}">{2}</div>'

        html_lines = [(linet.format(' highlight' if line_no in highlight_lines else '', line_no, line))
                      for line_no, line in enumerate(html_lines, (start_line or 0))]

        return "".join(html_lines).replace('\n', '<br>')


class Highlighter(with_metaclass(HighlighterMeta, HighlighterType)):
    pass


class TextHighlighter(Highlighter):
    format = "text"


class XMLHighlighter(Highlighter):
    format = "xml"

    styles = [
        r'(?P<comment><!--.*?-->)|(?P<tag><(?P<xmlns>\w*?:)?(?P<tagname>[\w\-]*)(?P<tagcontent>.*?)(?P<endtagname>/[\w\-:]*?)?>)',
        r'\s\S*?=(?P<attrib>\".*?\")',
        r'(?P<braced>\{.*?\})',
        r'(?P<sub>\$\{.*?\})',
        r'(?P<cdata>\<\!\[CDATA\[.*?\]\]\>)'
    ]


class PythonHighlighter(Highlighter):
    format = "python"

    styles = [
        r'\b(?P<keyword>yield|is|print|raise|pass|and|or|not|return|def|class|import|from|as|for|in|try|except|with|finally|if|else|elif|while)\b',
        r'\b(?P<constant>None|True|False)\b',
        r'\b(?P<builtin>open|file|str|repr|bytes|unicode|int)\b',
        r'\b\((?P<call>.*?)\)',

        r'\b((?:def|class)\s+(?P<def>\w+))',


        #('string', r'(".*?(?<!\\)")'),
        #('string', r'(""".*?""")'),
        #('string', r"('.*?(?<!\\)')"),
        #('string', r"('''.*?''')"),
        r'(?P<self>self)',
        r'\b(?P<number>\d+)',
        r'(?P<operator>\W+)',
        r'\b(?P<operator>or|and|in)\b',
        r'(?P<brace>\(|\)|\[|\]|\{|\})',
        r'@(?P<decorator>[\w\.]*)',

        r'(?P<comment>#.*?)$|(?P<string>(?:""".*?""")|(?:"(?:\\.|.)*?")' + r"|(?:'''.*?''')|(?:'(?:\\.|.)*?'))",

    ]


class HTMLHighlighter(Highlighter):
    format = "html"

    styles = [
        r'(?P<comment><!--.*?-->)|(?P<tag><(?P<xmlns>\w*?:)?(?P<tagname>\w*)(?P<tagcontent>.*?)(?P<endtagname>/\w*?)?>)',
        r'\s\S*?=(?P<attrib>\".*?\")',
    ]


class MoyatemplateHighlighter(Highlighter):
    format = "moyatemplate"

    styles = [
        r'(?P<comment><!--.*?-->)|(?P<tag><(?P<xmlns>\w*?:)?(?P<tagname>\w*)(?P<tagcontent>.*?)(?P<endtagname>/\w*?)?>)',
        r'\s\S*?=(?P<attrib>\".*?\")',

        r'(?P<sub>\$\{.*?\})',
        r'(?P<templatetag>{%.*?%})'
    ]


class RouteHighlighter(Highlighter):
    format = "route"
    styles = [
        r'(?P<special>\{.*?\})'
    ]


class TargetHighlighter(Highlighter):
    line_anchors = False
    format = "target"
    styles = [
        r'(?P<libname>[\w\.\-]+?)(?P<hash>\#)(?P<elementname>[\w\.\-]+)',
    ]


class INIHighlighter(Highlighter):
    line_anchors = False
    format = "ini"
    styles = [
        r'^(?P<key>.*?)=(?P<value>.*?)$',
        r'^(\s+)(?P<value>.*?)$',
        r'^(?P<section>\[.*?\])$',
        r'^(?P<section>\[(?P<sectiontype>.*?)\:(?P<sectionname>.*?)\])$',
        r'^(?P<comment>#.*?)$'
    ]


class JSHighligher(Highlighter):
    format = "js"
    styles = [
        r'(?P<keyword>this|function|var|new|alert)',
        r'\b(?P<constant>null|true|false)\b',
        r'\b(?P<number>\d+)',
        r'(?P<operator>\W+)',
        r'\b(?P<operator>\|\||\&\&|\+|\-|\*|\/)\b',
        r'(?P<brace>\(|\)|\[|\]|\{|\})',
        r'(?P<string>".*?")',
        r'(?P<string>\'.*?\')',
        r'(?P<comment>\/\*.*?\*\/)'
    ]


class Formatter(object):

    def __init__(self, lineno=True):
        self.lineno = lineno


class HTMLFormatter(Formatter):
    pass


class SyntaxFilter(MoyaFilterBase):
    def __moyafilter__(self, context, app, value, params):
        lang = params.pop('lang', None)
        value = dedent(remove_padding(text_type(value.strip('\n'))))
        code = highlight(lang, value, line_numbers=False)
        return HTML('<pre class="moya-console format-{lang}"">{code}</pre>'.format(lang=lang, code=code))


if __name__ == "__main__":
    code = open("console.py", "rb").read()
    code = code.decode('utf-8')
    html = highlight("python", code)
    with timer("highlight", ms=True):
        html = highlight("python", code)
    with open("syntaxtest.html", 'wt') as f:
        f.write(html.encode('utf-8'))
