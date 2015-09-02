# PY3 + PY2
from __future__ import unicode_literals
from __future__ import print_function

from moya.compat import text_type

import re
import unicodedata

_re_html = re.compile(r'<.*?>|\&.*?\;', re.UNICODE | re.DOTALL)
_re_link = re.compile(r'((?:http://|https://|mailto:)[\@\w\.\/]+)', re.UNICODE)
_re_spaceless = re.compile(r'>\s+<')


def escape(text):
    """Escape text for inclusion in html"""
    return text_type(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", "&#39;")


def slugify(value):
    # Borrowed from Django
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub('[^\w\s-]', '', value).strip().lower()
    return re.sub('[-\s]+', '-', value)


def textilize(s):
    """Remove markup from html"""
    s = s.replace("<p>", " ").replace('&nbsp;', ' ')
    return _re_html.sub("", s)


def spaceless(s, _re=_re_spaceless):
    """Remove spaces between tags"""
    return _re.sub("><", s)


def summarize(s, max_size=100):
    s = textilize(s)

    if len(s) > max_size:
        if not s[max_size].isspace():
            words = s[:max_size].split()
            words.pop()
        else:
            words = s[:max_size].split()
        s = escape(' '.join(words)) + ' [&hellip;]'
    else:
        s = escape(s)
    return s


def linebreaks(text):
    """Replace new lines with <br>"""
    html = "<br>\n".join(escape(text_type(text)).splitlines())
    return html


def linkify(text):
    def make_link(link):
        if link.startswith('http://') or link.startswith('https://'):
            if link.endswith('.'):
                return '<a href="{}" rel="nofollow">{}</a>.'.format(link[:-1], escape(link[:-1]))
            else:
                return '<a href="{}" rel="nofollow">{}</a>'.format(link, escape(link))
        else:
            email = escape(link.partition(':')[-1])
            if email.endswith('.'):
                return '<a href="mailto:{0}">{0}</a>.'.format(email[:-1])
            else:
                return '<a href="mailto:{0}">{0}</a>'.format(email)

    lines = []
    for line in text.splitlines():
        tokens = []
        pos = 0
        for match in _re_link.finditer(line):
            text = match.group(0)
            start, end = match.span(0)
            if start > pos:
                tokens.append(escape(line[pos:start]))
            tokens.append(make_link(text))
            pos = end
        if pos < len(line):
            tokens.append(escape(line[pos:]))
        lines.append(''.join(tokens))

    return "<br>".join(lines)


if __name__ == "__main__":

    print(spaceless("<b>   <i>   aasd </i>   </b>"))

    print(escape("10 > 5 < 8 & foo"))

    print(summarize('Hello <a href="#">test</a> werwer'))

    print(linkify("My homepage is http://willmcgugan.com/asdd.\nmailto://willmcgugan@gmail.com yadda yadda mailto:willmcgugan@gmail.com "))
    # from moya.tools import timer, MultiReplace

    # replace = MultiReplace({'&': '&amp;', '<' : '&lt;', '>' : '&gt;', '"': '&quote;', "'": "&#39"})

    # text = '''Some "text" & 'stuff'<>'''

    # REPEAT = xrange(100000)


    # with timer('chained escape'):
    #     for _ in REPEAT:
    #         escape(text)

    # with timer('multi escape'):
    #     for _ in REPEAT:
    #         replace(text)
