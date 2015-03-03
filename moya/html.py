# PY3 + PY2
from __future__ import unicode_literals
from __future__ import print_function

from moya.compat import text_type

import re
import unicodedata

_re_html = re.compile(r'<.*?>|\&.*?\;', re.UNICODE | re.DOTALL)


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


if __name__ == "__main__":
    print(escape("10 > 5 < 8 & foo"))

    print(summarize('Hello <a href="#">test</a> werwer'))

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
