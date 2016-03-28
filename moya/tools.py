from __future__ import unicode_literals
from __future__ import print_function

from time import time
from datetime import datetime
from contextlib import contextmanager
from random import choice
from functools import reduce
from calendar import timegm

from os.path import abspath, dirname, join, isfile, basename
import re
import os
import sys
import hashlib

from .compat import zip_longest, iteritems, xrange, text_type, PY3, implements_to_string, number_types


_re_xml_namespace = re.compile(r'^\{(.*?)\}(.*)$', re.UNICODE)


def extract_namespace(tag_name, default='http://moyaproject.com', _namespace_match=_re_xml_namespace.match):
    """Extracts namespace and tag name in Clark's notation"""
    match = _namespace_match(tag_name)
    if match is None:
        return default, tag_name
    return match.group(1) or default, match.group(2)


def asint(value, default=None):
    """Convert to an integer where possible, or return a default"""
    try:
        return int(value)
    except:
        return default


def match_exception(exception, catch_type):
    """Match an exception with a catch type wildcard"""
    for c, e in zip_longest(catch_type.split('.'),
                            exception.split('.'),
                            fillvalue=None):
        if c == '*':
            return True
        if c != e:
            return False
    return True


def md5_hexdigest(text):
    m = hashlib.md5()
    m.update(text.encode('utf-8'))
    if PY3:
        return m.hexdigest()
    else:
        return m.hexdigest().decode('utf-8')


def check_missing(map):
    for k, v in iteritems(map):
        if getattr(v, 'moya_missing', False):
            raise ValueError("value '{}' must not be missing (it is {!r})".format(k, v))


@contextmanager
def timer(msg="elapsed", ms=False, write_file=None, output=sys.stdout.write):
    """Context manager to time a block of code"""
    now = datetime.now()
    start = time()
    yield
    taken = (time() - start)
    if ms:
        output("%s: %.2fms\n" % (msg, taken * 1000))
    else:
        output("%s: %.2fs\n" % (msg, taken))
    if write_file is not None:
        import socket
        hostname = socket.gethostname()
        with open(write_file, 'a+') as f:
            f.write('%s,%.2f,"%s","%s"\n' % (now.ctime(), taken, msg, hostname))


class TimeDeltaParser(object):
    """Convert a text description of a time span in to milliseconds"""
    _re_td = re.compile(r'(\d+?)(ms|s|m|h|d)?$')
    _to_ms = dict(ms=1,                   # milliseconds
                  s=1000,                 # seconds
                  m=1000 * 60,            # minutes
                  h=1000 * 60 * 60,       # hours
                  d=1000 * 60 * 60 * 24)  # days

    @classmethod
    def parse(cls, s):
        """Convert a timedelta string to an integer of milliseconds,
        or return None if the string is not in the appropriate format.

        """
        match = cls._re_td.match(s)
        if match is None:
            raise ValueError("'{}' is not a valid timespan".format(s))
        t, unit = match.groups()
        t = int(t) * cls._to_ms.get(unit or 'ms')
        return t

parse_timedelta = TimeDeltaParser.parse


def get_moya_dir(path=None):
    """Searches current directory and ancestors for a directory containing
    a file called 'moya' -- or None if no path is found.

    """
    if path is None:
        path = os.getcwd()
    path = abspath(path)
    while not isfile(join(path, 'moya')):
        if basename(path) in ('', '/'):
            raise ValueError("Moya project directory not found")
        path = dirname(path)
    return path


def is_moya_dir(path=None):
    """Check if a path is a moya project"""
    if path is None:
        path = os.curdir
    path = abspath(path.replace('\\', '/'))
    return isfile(join(path, 'moya'))


def file_chunker(f, size=2 * 16 * 1024):
    """An iterator that reads a file in chunks."""
    read = f.read
    chunk = read(size)
    while chunk:
        yield chunk
        chunk = read(size)
    f.close()


def make_id():
    """Make a unique id."""
    _ID_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "{:0X}{}".format(int(time() * 1000.0), ''.join(choice(_ID_CHARS) for _ in xrange(6)))


def datetime_to_epoch(d):
    if isinstance(d, number_types):
        return int(d)
    return timegm(d.utctimetuple())


def split_commas(s):
    """Split a string on commas and return a list of tokens"""
    return [token.strip() for token in s.split(',') if token]


def summarize_text(text, max_length=100, marker='[...]'):
    """Truncate text and add a marker, if the length is above `max_langth`"""
    if not text:
        return ''
    if len(text) < max_length:
        return text
    return text[:max_length] + marker


def get_return(value):
    if value is None:
        return {}
    if hasattr(value, 'get_return_value'):
        return value.get_return_value()
    return value


def as_dict(value):
    if isinstance(value, dict):
        return value
    return dict(iteritems(value))


def as_text(value):
    """Convert to string, treating None as empty string."""
    return '' if value is None else text_type(value)


def quote(text):
    """Return a string surrounded by quotes"""
    # This may be trivial, but it can make code more self-documenting
    return '"{}"'.format(text)


def squote(text):
    """Return a string surrounded by single quotes"""
    return "'{}'".format(text)


def textual_list(items, join_word='or', empty="(nothing)"):
    """Lists items in humanized list form.

    e.g.
    >>> textual_list(['foo', 'bar', 'baz'])
    'foo', 'bar' or 'baz'

    """
    if not items:
        return empty
    items = list(items)
    last_item = items.pop()
    items_list = ", ".join("'{}'".format(item) for item in items)
    if items:
        return "{} {} {}".format(items_list, join_word, "'{}'".format(last_item))
    else:
        return "'{}'".format(last_item)


def moya_update(map, values):
    (getattr(map, '__moyaupdate__', None) or getattr(map, 'update'))(values)


def url_join(*urls):
    """Combine url segments"""
    return reduce(lambda p1, p2: '{}/{}'.format(p1.rstrip('/'), p2.lstrip('/')), urls)


def remove_padding(text):
    """remove any blank (all whitespace) lines at the beginning and end of text"""
    if text.isspace() or not text:
        return ''
    lines = text.splitlines()
    padding_start = 0
    padding_end = 0
    iter_lines = iter(lines)
    while (next(iter_lines) or ' ').isspace():
        padding_start += 1
    iter_lines = iter(reversed(lines))
    while (next(iter_lines) or ' ').isspace():
        padding_end -= 1
    return '\n'.join(lines[padding_start or None:padding_end or None])


def unique(v):
    """Generates a list from a sequence where each value appears only once, and the order is preserved."""
    try:
        sequence = list(v)
    except:
        return []
    seen = set()
    seen_add = seen.add
    return [item for item in sequence if not (item in seen or seen_add(item))]


def format_element_type(element_type):
    if isinstance(element_type, text_type):
        return element_type
    ns, et = element_type
    return "{" + ns + "}" + et


def decode_utf8_bytes(text, errors='ignore'):
    """Decode bytes as utf-8, returns unicode unaltered."""
    if isinstance(text, bytes):
        return text.decode('utf-8', errors=errors)
    return text


# def get_ids(seq):
#     """Get ID attributes from a sequence"""
#     return [item.id for item in seq if hasattr(seq, 'id')]


class MultiReplace(object):
    """Replace multiple tokens at once"""
    # Note, this typically slower than chained calles to .replace
    def __init__(self, replace_map):
        self.get_replace = replace_map.__getitem__
        self._re = re.compile("|".join(re.escape(k) for k in replace_map.keys()))
        self.sub = self._re.sub

    def __call__(self, text):
        get_replace = self.get_replace
        return self.sub(lambda match: get_replace(match.group(0)), text)


class DummyLock(object):
    """Replacement for real lock that does nothing"""
    def __enter__(self):
        pass

    def __exit__(self, *args, **kwargs):
        pass


def make_cache_key(key_data):
    if not isinstance(key_data, (list, tuple)):
        key_data = [key_data]
    key = []
    append = key.append
    for component in key_data:
        if isinstance(component, text_type):
            append(component)
        elif isinstance(component, list):
            append('-'.join(make_cache_key(k) for k in component))
        elif isinstance(component, set):
            append('-'.join(make_cache_key(k) for k in sorted(component)))
        elif isinstance(component, dict):
            append('-'.join("{}_{}".format(k, make_cache_key([v])) for k, v in sorted(component.items())))
        else:
            append(text_type(component))
    return '.'.join(key)


# http://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Levenshtein_distance#Python
def levenshtein(seq1, seq2):
    """Levenshtein word distance"""
    oneago = None
    thisrow = list(range(1, len(seq2) + 1)) + [0]
    for x in xrange(len(seq1)):
        twoago, oneago, thisrow = oneago, thisrow, [0] * len(seq2) + [x + 1]
        for y in xrange(len(seq2)):
            delcost = oneago[y] + 1
            addcost = thisrow[y - 1] + 1
            subcost = oneago[y - 1] + (seq1[x] != seq2[y])
            thisrow[y] = min(delcost, addcost, subcost)
    return thisrow[len(seq2) - 1]


def nearest_word(word, words, min_distance=3):
    """Find the nearest word from a list, within a given Levenshtein distance"""
    compare = []
    for compare_word in words:
        d = levenshtein(word, compare_word)
        if d < min_distance:
            compare.append((d, compare_word))
    if not compare:
        return None
    return sorted(compare)[0][1]


def show_tb(f):
    """Decorator that print tracebacks from functions that may otherwise end up hiding them"""
    def deco(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            import traceback
            traceback.print_exc(e)
            raise
    return deco


def normalize_url_path(p):
    """Makes sure a URL path starts and ends with a forward slash"""
    if not p.startswith('/'):
        p = '/' + p
    if not p.endswith('/'):
        p = p + '/'
    return p


@implements_to_string
class lazystr(object):
    """convert to a string lazily, for use in logging"""
    def __init__(self, _callable, *args, **kwargs):
        self._callable = _callable
        self._args = args
        self._kwargs = kwargs
        self._str = None

    def __str__(self):
        if self._str is None:
            self._str = text_type(self._callable(*self._args, **self._kwargs))
        return self._str

    def __len__(self):
        return len(text_type(self))

    def __getattr__(self, k):
        return getattr(text_type(self), k)

