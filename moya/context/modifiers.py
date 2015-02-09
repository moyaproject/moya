from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from decimal import Decimal

from ..versioning import Version, VersionSpec
from ..url import URL
from ..compat import (text_type,
                      string_types,
                      int_types,
                      number_types,
                      unichr,
                      urlencode)
from ..html import slugify, textilize
from ..render import HTML
from ..context.tools import get_moya_interface, get_moya_attribute, obj_index
from ..context.expressiontime import (TimeSpan,
                                      ExpressionDateTime,
                                      ExpressionDate,
                                      ExpressionTime)
from ..containers import QueryData
from ..context.tools import to_expression
from ..context.missing import Missing
from ..tools import unique
from ..reader import ReaderError
from .. import connectivity
from .. import moyajson

from fs.path import (basename,
                     pathjoin,
                     relativefrom,
                     dirname,
                     splitext)


import hashlib
from collections import OrderedDict
from datetime import datetime
from operator import truth
from math import ceil, floor, log

import copy


class Path(text_type):
    """Magic for paths"""
    def __truediv__(self, other):
        return Path(pathjoin(self, text_type(other)))

    def __rtruediv__(self, other):
        return Path(pathjoin(self, text_type(other)))


class ExpressionModifiersBase(object):
    """Implementations for expression filters"""

    @classmethod
    def is_missing(cls, val):
        """Check if a value is the special 'missing' value"""
        return getattr(val, 'moya_missing', False)

    @classmethod
    def moya_localize(cls, context, obj):
        locale = context.get('.locale', None)
        if isinstance(obj, datetime):
            obj = ExpressionDateTime.from_datetime(obj)
        if locale and hasattr(obj, '__moyalocalize__'):
            return obj.__moyalocalize__(context, locale)
        return text_type(obj)

    @classmethod
    def _lookup_key(cls, obj, key, default=None):
        if hasattr(obj, '__getitem__') and hasattr(obj, 'get'):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @classmethod
    def _keys(cls, context, obj):
        if cls.is_missing(obj):
            return []
        if hasattr(obj, '__getitem__'):
            if hasattr(obj, 'keys'):
                return list(obj.keys())
            else:
                return [i for i, _v in enumerate(obj)]
        else:
            return [k for k in dir(obj) if not k.startswith('_')]

    @classmethod
    def _values(cls, context, obj):
        if cls.is_missing(obj):
            return []
        if hasattr(obj, '__getitem__'):
            if hasattr(obj, 'values'):
                return [get_moya_interface(context, v) for v in obj.values()]
            else:
                return obj[:]
        else:
            return [get_moya_attribute(context, obj, k) for k in dir(obj) if not k.startswith('_')]

    @classmethod
    def _items(cls, context, obj):
        if cls.is_missing(obj):
            return []
        if hasattr(obj, '__getitem__'):
            if hasattr(obj, 'items'):
                return [(k, get_moya_interface(context, v)) for k, v in obj.items()]
            else:
                return [(i, get_moya_interface(context, v)) for i, v in enumerate(obj)]
        else:
            obj_items = []
            for k in dir(obj):
                if k.startswith('_'):
                    continue
                try:
                    obj_items.append((k, get_moya_interface(context, getattr(obj, k, Missing(k)))))
                except:
                    # Getting the attribute has thrown an exception
                    # Nothing we can do but ignore it
                    obj_items.append((k, None))
            return obj_items

    @classmethod
    def _map(cls, obj):
        return dict(obj)

    @classmethod
    def _flat(cls, obj):
        result = []
        for value in obj:
            if hasattr(value, '__iter__'):
                result.extend(value)
            else:
                result.append(value)
        return result

    @classmethod
    def _to_query_list(cls, d):
        """Ensures a dictionary contains lists"""
        return [(k, v if isinstance(v, list) else [v]) for k, v in d.items()]

    @classmethod
    def _urlencode(cls, data):
        if not hasattr(data, 'items'):
            raise ValueError("Can't urlencode {!r}".format(data))
        return urlencode(cls._to_query_list(data), doseq=True)

    @classmethod
    def _qsupdate(cls, context, data, base_qs=None):
        if base_qs is None:
            base_qs = context.get('.request.query_string', '')
        current_data = QueryData.from_qs(base_qs)
        current_data.update(data)
        return cls._urlencode(current_data)

    @classmethod
    def _filesize(cls, size):
        try:
            size = int(size)
        except:
            raise ValueError("filesize requires a numeric value, not {!r}".format(size))
        suffixes = ('kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB')
        base = 1024
        if size == 1:
            return '1 byte'
        elif size < base:
            return '{:,} bytes'.format(size)

        for i, suffix in enumerate(suffixes):
            unit = base ** (i + 2)
            if size < unit:
                return "{:,.01f}{}".format((base * size / unit), suffix)
        return "{:,.01f}{}".format((base * size / unit), suffix)

    @classmethod
    def _permission(cls, context, v):
        if not v:
            return True
            #return bool(context['.user'])
        permissions = context['.permissions']
        if isinstance(v, list):
            return all(text_type(p) in permissions for p in v)
        else:
            return text_type(v) in permissions

    @classmethod
    def _validfloat(cls, context, v):
        try:
            float(text_type(v))
        except:
            return False
        else:
            return True

    @classmethod
    def _validinteger(cls, context, v):
        try:
            int(text_type(v))
        except:
            return False
        return True

    @classmethod
    def _seqlast(cls, v, context):
        """Iterate over a sequence, returning the item and a flag that indicates if it is the last item"""
        seq = list(v)
        last = len(v) - 1
        return [(i == last, i) for i, l in enumerate(seq)]

    @classmethod
    def _count(cls, seq):
        if hasattr(seq, 'count'):
            return seq.count()
        return len(seq)


class ExpressionModifiers(ExpressionModifiersBase):

    def abs(self, context, v):
        return abs(v)

    def all(self, context, v):
        return all(bool(i) for i in v)

    def any(self, context, v):
        return any(bool(i) for i in v)

    def basename(self, context, v):
        return basename(v)

    def bool(self, context, v):
        return truth(v)

    def capitalize(self, context, v):
        return text_type(v).capitalize()

    def ceil(self, context, v):
        return ceil(float(v))

    def chr(self, context, v):
        try:
            return unichr(v)
        except TypeError:
            return v

    def collect(self, context, v):
        seq, key = v
        return [obj_index(obj, key) for obj in seq]

    def collectids(self, context, v, _lookup_key=ExpressionModifiersBase._lookup_key):
        return [_item for _item in (_lookup_key(item, 'id', Ellipsis) for item in v) if _item is not Ellipsis]

    def commalist(self, context, v):
        return ",".join(text_type(s) for s in v)

    def commaspacelist(self, context, v):
        return ", ".join(text_type(s) for s in v)

    def commasplit(self, context, v):
        return [t for t in text_type(v).split(',') if t]

    def copy(self, context, v):
        if hasattr(v, 'copy'):
            return v.copy()
        return copy.copy(v)

    def d(self, context, v):
        return Decimal(v)

    def data(self, context, v):
        try:
            data_fs = context['.fs']['data']
        except KeyError:
            raise ValueError("missing 'data' filesystem")
        try:
            data = data_fs.reader.read(v, app=context.get('.app', None))
        except ReaderError:
            raise
        return data

    def date(self, context, v):
        return ExpressionDate.from_isoformat(v)

    def datetime(self, context, v):
        return ExpressionDateTime.from_isoformat(v)

    def debug(self, context, v):
        return to_expression(context, v)

    def dict(self, context, v):
        if isinstance(v, list):
            items = v
        else:
            items = self._items(context, v)
        try:
            return OrderedDict(items)
        except:
            return {}

    def dirname(self, context, v):
        return dirname(v)

    def enum(self, context, v):
        key = text_type(v)
        return context['.enum'].get(key, None)

    def enumerate(self, context, v):
        return enumerate(v)

    def enumerate1(self, context, v):
        return enumerate(v, start=1)

    def eval(self, context, v):
        from .expression import Expression
        return Expression(v).eval(context)

    def exists(self, context, v):
        return not getattr(v, 'moya_missing', False)

    def ext(self, context, v):
        return splitext(v)[1].lstrip('.')

    def filesize(self, context, v):
        return self._filesize(v)

    def first(self, context, v):
        try:
            return v[0]
        except IndexError:
            return None

    def flat(self, context, v):
        return self._flat(v)

    def float(self, context, v):
        return float(v)

    def floor(self, context, v):
        return floor(float(v))

    def fromjson(self, context, v):
        try:
            return moyajson.loads(v)
        except:
            return None

    def get(self, context, v):
        try:
            return connectivity.get(v)
        except:
            return None

    def hasdata(self, context, v):
        try:
            data_fs = context['.fs']['data']
        except KeyError:
            raise ValueError("missing 'data' filesystem")
        return data_fs.reader.exists(text_type(v))

    def html(self, context, v):
        return HTML(v)

    def ids(self, context, v):
        try:
            return [item.id for item in v if hasattr(v, 'id')]
        except:
            return []

    def int(self, context, v):
        try:
            return int(v)
        except Exception:
            return None

    def isbool(self, context, v):
        return isinstance(v, bool)

    def isemail(self, context, v):
        email = text_type(v)
        return '@' in email and '.' in email

    def isfloat(self, context, v):
        return isinstance(v, float)

    def isint(self, context, v):
        return isinstance(v, int_types)

    def isnone(self, context, v):
        return v is None

    def isnumber(self, context, v):
        return isinstance(v, number_types)

    def isstr(self, context, v):
        return isinstance(v, string_types)

    def items(self, context, v):
        return self._items(context, v)

    def join(self, context, v):
        return ''.join(text_type(i) for i in v)

    def keys(self, context, v):
        return self._keys(context, v)

    def last(self, context, v):
        try:
            return v[-1]
        except IndexError:
            return None

    def len(self, context, v):
        return len(v)

    def list(self, context, v):
        try:
            return list(v)
        except Exception:
            return []

    def localize(self, context, v):
        return self.moya_localize(context, v)

    def log10(self, content, v):
        return log(float(v), 10)

    def lower(self, context, v):
        return text_type(v).lower()

    def lstrip(self, context, v):
        return text_type(v).lstrip()

    def map(self, context, v):
        return self._map(v)

    def max(self, context, v):
        return max(v)

    def md5(self, context, v):
        if hasattr(v, 'read'):
            m = hashlib.md5()
            while 1:
                chunk = v.read(16384)
                if not chunk:
                    break
                m.update(chunk)
            try:
                v.seek(0)
            except:
                pass
            return m.hexdigest()

        if isinstance(v, text_type):
            v = v.encode('utf-8')
        return hashlib.md5(v).hexdigest()

    def min(self, context, v):
        return min(v)

    def missing(self, context, v):
        return getattr(v, 'moya_missing', False)

    def none(self, context, v):
        if not v:
            return None
        return v

    def path(self, context, v):
        return Path(v)

    def permission(self, context, v):
        return self._permission(context, v)

    def prettylist(self, context, v):
        return ", ".join("'{}'".format(text_type(s)) for s in v)

    def qsupdate(self, context, v):
        return self._qsupdate(context, v)

    def quote(self, context, v):
        return '"{}"'.format(text_type(v))

    def relto(self, context, v):
        base = dirname(context.get('.request.path', '/'))
        return relativefrom(base, text_type(v))

    def renderable(self, context, v):
        return getattr(v, '__moyarenderable__', lambda c: v)(context)

    def remap(self, context, v):
        items = self._items(context, v)
        remap = {}
        for k, v in items:
            remap.setdefault(v, []).append(k)
        return remap

    def reversed(self, context, v):
        return list(reversed(v))

    def reversesorted(self, context, v):
        return sorted(v, reverse=True)

    def round(self, context, v):
        try:
            n, r = v
        except:
            r = 0.0
        n = float(n)
        r = int(r)
        return round(n, r)

    def rstrip(self, context, v):
        return text_type(v).rstrip()

    def seqlast(self, context, v):
        return self._seqlast(v, context)

    def set(self, context, v):
        return set(v)

    def slice(self, context, v):
        return slice(*v)

    def slug(self, context, v):
        return slugify(v)

    def sorted(self, context, v):
        return sorted(v)

    def split(self, context, v):
        split_on = None
        if isinstance(v, list):
            try:
                v, split_on = v
            except:
                pass
        v = text_type(v)
        return v.split(split_on)

    def splitfirst(self, context, v):
        try:
            return self.split(context, v)[0]
        except IndexError:
            raise ValueError('splitfirst has nothing to return')

    def splitlast(self, context, v):
        try:
            return self.split(context, v)[-1]
        except IndexError:
            raise ValueError('splitlast has nothing to return')

    def splitlines(self, context, v):
        return text_type(v).splitlines()

    def squote(self, context, v):
        return "'{}'".format(text_type(v))

    def str(self, context, v):
        if v is None:
            return ''
        return text_type(v)

    def strip(self, context, v):
        return text_type(v).strip()

    def striphtml(self, context, v):
        v = text_type(v)
        return textilize(v)

    def sub(self, context, v):
        text = text_type(v)
        return context.sub(text)

    def sum(self, context, v):
        # Moya sum is fairly forgiving in comparison to Python sum
        iter_v = iter(v)
        first = None
        try:
            first = next(iter_v)
            first_type = type(first)
            while 1:
                first += first_type(next(iter_v))
        except StopIteration:
            pass
        return first

    def swapcase(self, context, v):
        return text_type(v).swapcase()

    def time(self, context, v):
        return ExpressionTime.from_isoformat(v)

    def timespan(self, context, v):
        return TimeSpan(v)

    def title(self, context, v):
        return text_type(v).title()

    def json(self, context, v):
        return moyajson.dumps(v)

    def type(self, context, v):
        return type(v)

    def unique(self, context, v):
        return unique(v)

    def upper(self, context, v):
        return text_type(v).upper()

    def url(self, context, v):
        from ..url import URL
        return URL(v)

    def urldecode(self, context, v):
        return QueryData.from_qs(text_type(v))

    def urlencode(self, context, v):
        return self._urlencode(v)

    def urlupdate(self, context, v):
        if isinstance(v, list):
            url = URL(text_type(v[0]))
            data = v[1]
        else:
            url = URL(context['.request.path_qs'])
            data = v
        url.query.update(data)
        return text_type(url)

    def validfloat(self, context, v):
        return self._validfloat(context, v)

    def validint(self, context, v):
        return self._validinteger(context, v)

    def values(self, context, v):
        return self._values(context, v)

    def version(self, context, v):
        try:
            return Version(text_type(v))
        except:
            return None

    def versionspec(self, context, v):
        try:
            return VersionSpec(text_type(v))
        except:
            return None

    def zip(self, content, v):
        return zip(*v)
