"""
A moya context object to represent a URL

"""

from __future__ import unicode_literals
from __future__ import print_function


from .containers import QueryData
from .urltools import urlencode
from .interface import AttributeExposer
from .compat import implements_to_string, text_type, PY2

if PY2:
    from urlparse import urlsplit, urlunsplit, urljoin
else:
    from urllib.parse import urlsplit, urlunsplit, urljoin


def get_domain(url):
    """Get a domain from a URL or empty string"""
    if not isinstance(url, text_type):
        return ''
    netloc = urlsplit(url).netloc
    if ':' in netloc:
        domain = netloc.split(':', 1)[0]
    else:
        domain = netloc
    return domain


class _Exposed(object):
    def __init__(self, name):
        self.attribute_name = "_" + name

    def __get__(self, obj, objtype):
        return getattr(obj, self.attribute_name)

    def __set__(self, obj, val):
        setattr(obj, self.attribute_name, val)


@implements_to_string
class URL(AttributeExposer):
    __moya_exposed_attributes__ = ["scheme",
                                   "netloc",
                                   "path",
                                   "qs",
                                   "query",
                                   "fragment",
                                   "base",
                                   "no_fragment",
                                   "no_scheme",
                                   "with_slash",
                                   "parent_dir",
                                   "resource"]

    def __init__(self, url):
        super(URL, self).__init__()
        self._url = text_type(url)
        split_url = urlsplit(url, allow_fragments=True)
        (self._scheme,
         self._netloc,
         self._path,
         self._qs,
         self._fragment) = split_url

        self._query_dict = QueryData.from_qs(self._qs, change_callback=self._changed)

    scheme = _Exposed("scheme")
    netloc = _Exposed("netloc")
    path = _Exposed("path")
    qs = _Exposed("qs")
    fragment = _Exposed("fragment")

    def _changed(self):
        self._modified = True

    def __repr__(self):
        return '<URL "{}">'.format(self)

    def __str__(self):
        self._qs = text_type(self._query_dict)
        parts = (self.scheme,
                 self.netloc,
                 self.path,
                 self.qs,
                 self.fragment)
        return urlunsplit(parts)

    def __moyaconsole__(self, console):
        console(self.scheme + '://', fg="blue")(self.netloc, fg="green")(self.path, italic=True)
        if self.qs:
            console('?' + self.qs, fg="blue", bold=True)
        if self.fragment:
            console('#' + self.fragment, fg="magenta", bold=True)
        console.nl()

    def __moyarepr__(self, context):
        return "url:'{}'".format(text_type(self))

    def join(self, path):
        return URL(urljoin(self, path))

    def __truediv__(self, path):
        return self.join(text_type(path))

    def __div__(self, path):
        return self.join(text_type(path))

    @property
    def base(self):
        parts = (self.scheme,
                 self.netloc,
                 self.path,
                 '',
                 '')
        return URL(urlunsplit(parts))

    @property
    def no_fragment(self):
        parts = (self.scheme,
                 self.netloc,
                 self.path,
                 self.qs,
                 '')
        return URL(urlunsplit(parts))

    @property
    def no_scheme(self):
        parts = ('',
                 self.netloc,
                 self.path,
                 self.qs,
                 self.fragment)
        return URL(urlunsplit(parts))

    @property
    def parent_dir(self):
        path = '/'.join(self.path.rstrip('/').split('/')[:-1]) + '/'
        parts = (self.scheme,
                 self.netloc,
                 path,
                 self.qs,
                 self.fragment)
        return URL(urlunsplit(parts))

    @property
    def with_slash(self):
        parts = (self.scheme,
                 self.netloc,
                 self.path.rstrip('/') + '/',
                 self.qs,
                 self.fragment)
        return URL(urlunsplit(parts))

    @property
    def qs(self):
        return self._qs

    @property
    def query(self):
        return self._query_dict

    @property
    def resource(self):
        return self.path.rsplit('/', 1)[-1]


if __name__ == "__main__":

    url = URL("http://moyaroject.com/foo/bar/baz")


    url.query['test'] = 'bar'

    print(url)

    url = URL('/foo/bar')

    print(url)

    url.query.update({'foo':'bar'})

    print(url)