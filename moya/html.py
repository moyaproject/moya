# PY3 + PY2
from __future__ import unicode_literals
from __future__ import print_function

from .compat import text_type

import re
import unicodedata

_re_html = re.compile(r'<.*?>|\&.*?\;', re.UNICODE | re.DOTALL)


def escape(text):
    """Escape text for inclusion in html"""
    return text_type(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def escape_quote(text):
    """Escape text for inclusion in html and within attributes"""
    return text_type(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


# # Borrowed from django
# def slugify(value):
#     if not isinstance(value, text_type):
#         value = text_type(value, 'utf-8')
#     value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
#     value = text_type(re.sub('[^\w\s-]', '', value).strip().lower())
#     return re.sub('[-\s]+', '-', value)

def slugify(value):
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
