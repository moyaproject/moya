"""A collection of tools for rendering information about xml (typically errors)"""
from __future__ import unicode_literals
from __future__ import print_function


def extract_lines(code, line, padding=2):
    """Extracts a number of lines from code surrounding a given line number,
    returns a list of tuples that contain the line number (1 indexed) and the line text.

    """
    lines = code.splitlines()
    start = max(0, line - padding - 1)
    end = min(len(lines), line + padding - 1)
    showlines = lines[start:end + 1]
    linenos = [n + 1 for n in range(start, end + 1)]
    return zip(linenos, showlines)


def extract(code, line, padding=3):
    lines = extract_lines(code, line, padding)
    start = lines[0][0]
    text = "\n".join(l[1] for l in lines)
    return start, text


def number(code, linestart=1, highlight_line=-1, number_wrap=None):
    if number_wrap is None:
        number_wrap = lambda n:n
    lines = code.splitlines()
    max_line = max(6, max(len(str(len(l))) for l in lines))
    out_lines = []
    for lineno, line in zip(range(linestart, linestart + len(lines)), lines):
        if lineno == highlight_line:
            number = ("*%i " % lineno).rjust(max_line)
        else:
            number = ("%i " % lineno).rjust(max_line)
        out_lines.append(number + line)
    return "\n".join(out_lines)


def column_to_spaces(line, col):
    """Returns the number of space required to reach a point in a string"""
    spaces = 0
    for colno, char in enumerate(line):
        spaces += 4 if col == '\t' else 1
        if colno + 1 == col:
            return spaces
    return spaces


def render_error(code, show_lineno, padding=3, col=None, colors=False, col_text="here"):

    lines = extract_lines(code, show_lineno, padding=padding)
    linenos = [str(lineno) for lineno, _ in lines]
    maxlineno = max(len(l) for l in linenos)

    render_lines = []
    for lineno, line in lines:
        if lineno == show_lineno:
            fmt = "*%s %s"
        else:
            fmt = " %s %s"
        render_lines.append(fmt % (str(lineno).ljust(maxlineno), line))
        if col is not None and lineno == show_lineno:
            point_at = column_to_spaces(line, col)
            pad = ' ' * (maxlineno + 1)
            if point_at > len(col_text) + 1:
                render_lines.append(pad + (col_text + " ^").rjust(point_at + 1))
            else:
                render_lines.append(pad + '^'.rjust(point_at + 1) + " " + col_text)

    return '\n'.join(line.replace('\t', ' ' * 4) for line in render_lines)


if __name__ == "__main__":
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

</moya>"""

    print(render_error(xml, 14, col=5))
