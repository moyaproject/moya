from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

from ..versioning import Version, VersionSpec
from ..url import URL, get_domain, urlencode
from ..compat import (text_type,
                      py2bytes,
                      string_types,
                      int_types,
                      number_types,
                      unichr,
                      implements_to_string)
from ..html import slugify, textilize, linebreaks, escape
from ..render import HTML, Safe
from ..context.tools import get_moya_interface, get_moya_attribute, obj_index
from ..context.expressiontime import (TimeSpan,
                                      ExpressionDateTime,
                                      ExpressionDate,
                                      ExpressionTime,
                                      epoch_to_datetime)
from .color import Color
from ..containers import QueryData
from ..context.tools import to_expression
from ..context.missing import Missing
from ..tools import unique, as_text, MultiReplace
from ..reader import ReaderError
from ..render import render_object
from .. import connectivity
from .. import moyajson
from ..import compat

from fs.path import (abspath,
                      basename,
                      join,
                      relativefrom,
                      dirname,
                      splitext)

import uuid
import hashlib
import copy
import collections
from base64 import b64decode, b64encode
from decimal import Decimal
from collections import OrderedDict
from datetime import datetime
from operator import truth
from itertools import chain
import random
from math import ceil, floor, log
import threading
import weakref


class Path(text_type):
    """Magic for paths."""

    def __truediv__(self, other):
        return Path(join(self, text_type(other)))

    def __rtruediv__(self, other):
        return Path(join(self, text_type(other)))


@implements_to_string
class Sentinel(object):
    """A singleton sentinel value."""

    _objects = weakref.WeakValueDictionary()
    _lock = threading.Lock()

    def __new__(cls, name):
        with cls._lock:
            if name in cls._objects:
                return cls._objects[name]
            else:
                obj = super(Sentinel, cls).__new__(cls)
                obj.name = name
                cls._objects[name] = obj
                return obj

    def __repr__(self):
        return "Sentinel('{s}')".format(self.name)

    def __moyarepr__(self, context):
        return "sentinel:'{}'".format(self.name)


def _slashjoin(paths):
    """Join paths with a slash."""
    paths = [text_type(p) for p in paths]
    _paths = [paths.pop(0).rstrip('/')]
    append = _paths.append
    for p in paths:
        append('/')
        append(p.lstrip('/'))
    return ''.join(_paths)


def make_uuid(context, version, nstype="url", nsname=None):

    _namespace_map = {
        "dns": uuid.NAMESPACE_DNS,
        "url": uuid.NAMESPACE_URL,
        "oid": uuid.NAMESPACE_OID,
        "x500": uuid.NAMESPACE_X500
    }
    namespace = _namespace_map.get(nstype, uuid.NAMESPACE_URL)
    if nsname is None and namespace == uuid.NAMESPACE_URL:
        namespace = context['.request.host_url']

    if version == 1:
        _uuid = uuid.uuid1()
    elif version == 3:
        _uuid = uuid.uuid3(namespace, nsname)
    elif version == 4:
        _uuid = uuid.uuid4()
    elif version == 5:
        _uuid = uuid.uuid5(namespace, nsname)

    return text_type(_uuid)


class ExpressionModifiersBase(object):
    """Implementations for expression filters."""

    @classmethod
    def is_missing(cls, val):
        """Check if a value is the special 'missing' value."""
        return getattr(val, 'moya_missing', False)

    @classmethod
    def moya_localize(cls, context, obj):
        if obj is None:
            return ''
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
        """Ensure a dictionary contains lists."""
        return [(k, v if isinstance(v, list) else [v]) for k, v in d.items()]

    @classmethod
    def _urlencode(cls, data):
        if not hasattr(data, 'items'):
            raise ValueError("Can't urlencode {}".format(data))
        return urlencode(data)

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
        suffixes = ('KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB')
        base = 1024.0
        if size == 1:
            return '1 byte'
        elif size < base:
            return '{:,} bytes'.format(size)

        for i, suffix in enumerate(suffixes):
            unit = base ** (i + 2)
            if size < unit:
                return "{:,.1f} {}".format((base * size / unit), suffix)
        return "{:,.1f} {}".format((base * size / unit), suffix)

    @classmethod
    def _permission(cls, context, v):
        if not v:
            return True
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
        else:
            return True

    @classmethod
    def _seqlast(cls, v, context):
        """Iterate over a sequence, returning the item and a flag that indicates if it is the last item."""
        seq = list(v)
        last = len(v) - 1
        return [(i == last, l) for i, l in enumerate(seq)]

    @classmethod
    def _count(cls, seq):
        if hasattr(seq, 'count'):
            return seq.count()
        return len(seq)


class ExpressionModifiers(ExpressionModifiersBase):
    """Functions exposed as modifiers in Moya expressions."""

    def abs(self, context, v):
        return abs(v)

    def abspath(self, context, v):
        return abspath(text_type(v))

    def all(self, context, v):
        return all(bool(i) for i in v)

    def any(self, context, v):
        return any(bool(i) for i in v)

    def app(self, context, v):
        """Get an application from a name or object."""
        app_name = v
        if hasattr(v, '__moya_application__'):
            return v.__moya_application__()
        app_name = text_type(v)
        archive = context['.app.archive']
        app = archive.find_app_default(app_name)
        return app

    def appname(self, context, v):
        """Get an application name."""
        if not isinstance(v, text_type):
            app = getattr(v, 'name', None)
        elif '.' in v:
            archive = context['.app.archive']
            app = archive.find_app_default(v)
            if app is not None:
                app = app.name
        else:
            app = v
        return app

    def appsettings(self, context, v):
        """Get an application from a name or object."""
        app_name = v
        if hasattr(v, '__moya_application__'):
            return v.__moya_application__()
        app_name = text_type(v)
        archive = context['.app.archive']
        app = archive.find_app_default(app_name)
        return getattr(app, 'settings')

    def base64encode(self, context, v):
        return b64encode(text_type(v))

    def base64decode(self, context, v):
        return b64decode(text_type(v))

    def basename(self, context, v):
        return basename(v)

    def bool(self, context, v):
        return truth(v)

    def capitalize(self, context, v):
        return text_type(v).capitalize()

    def ceil(self, context, v):
        return ceil(float(v))

    def choices(self, context, v):
        return getattr(v, 'choices', [])

    def intchoices(self, context, v):
        return getattr(v, 'intchoices', [])

    def chain(self, context, v):
        v = v if isinstance(v, collections.Iterable) else [v]
        return list(chain(*[i if isinstance(i, collections.Iterable) else [i] for i in v]))

    def chr(self, context, v):
        try:
            return unichr(v)
        except TypeError:
            return v

    def collect(self, context, v):
        seq, key = v
        return [obj_index(obj, key) for obj in seq]

    def collectmap(self, context, v):
        seq, key = v
        result = {}
        for obj in seq:
            try:
                k = obj_index(obj, key)
            except:
                pass
            else:
                result[k] = obj
        return result

    def collectids(self, context, v, _lookup_key=ExpressionModifiersBase._lookup_key):
        return [_item for _item in (_lookup_key(item, 'id', Ellipsis) for item in v) if _item is not Ellipsis] if v else []

    def color(self, context, v):
        return Color.construct(context, v)

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

    def count(self, context, v):
        try:
            seq, predicate = v
        except ValueError:
            raise ValueError('count: modifier expects [<seq>, <expression>]')
        if not hasattr(predicate, '__moyacall__'):
            raise ValueError('count: requires an expression, e.g. map:[students, {grade lt "A"}]')
        return sum(1 for item in seq if predicate.__moyacall__(item))

    def csrf(self, context, v):
        user_id = text_type(context['.session_key'] or '')
        form_id = text_type(v)
        secret = text_type(context['.secret'])
        raw_token = "{}{}{}".format(user_id, secret, form_id).encode('utf-8', 'ignore')
        m = hashlib.md5()
        m.update(raw_token)
        token_hash = m.hexdigest()
        return token_hash

    def d(self, context, v):
        if isinstance(v, Decimal):
            return v
        return Decimal(v)

    def data(self, context, v):
        if isinstance(v, list):
            try:
                app_name, path = v
            except:
                raise ValueError('data: requires list [<app>, <path]')
            path = text_type(path)
        else:
            app_name = None
            path = text_type(v)

        try:
            data_fs = context['.fs']['data']
        except KeyError:
            raise ValueError("missing 'data' filesystem")
        if app_name is not None:
            archive = context['.app.archive']
            app = archive.find_app_default(app_name)
        else:
            app = context.get('.app', None)
        try:
            data = data_fs.reader.read(path, app=app)
        except ReaderError:
            raise
        return data

    def date(self, context, v):
        if not v:
            return None
        if isinstance(v, text_type):
            return ExpressionDate.from_isoformat(v)
        else:
            return ExpressionDate.from_sequence(v)

    def datetime(self, context, v):
        if not v:
            return None
        if isinstance(v, ExpressionDateTime):
            return v
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

    def domain(self, context, v, _get_domain=get_domain):
        return _get_domain(text_type(v))

    # Candidate for removal
    def dropchar(self, context, v):
        return text_type(v)[1:]

    def enum(self, context, v):
        key = v
        if '#' in key:
            app, el = context['.app'].get_element(key)
            return context['.enum'].get(el.libid, None)
        else:
            return context['.app.lib.enum'].get(key, None)

    def enumerate(self, context, v):
        try:
            return enumerate(v)
        except:
            return []

    def enumerate1(self, context, v):
        try:
            return enumerate(v, start=1)
        except:
            return []

    def epoch(self, context, v):
        try:
            v = float(v)
        except ValueError:
            raise ValueError('unable to convert {} to a number'.format(context.to_expr(v)))
        dt = epoch_to_datetime(v)
        return ExpressionDateTime.from_datetime(dt)

    def escape(self, context, v):
        return escape(text_type(v))

    def eval(self, context, v):
        from .expression import Expression
        return Expression(v).eval(context)

    def exists(self, context, v):
        return not getattr(v, 'moya_missing', False)

    def ext(self, context, v):
        return splitext(v)[1].lstrip('.')

    def filesize(self, context, v):
        return self._filesize(v or 0)

    def filter(self, context, v):
        try:
            seq, predicate = v
        except ValueError:
            raise ValueError('filter: modifier expects [<seq>, <expression>]')
        if not hasattr(predicate, '__moyacall__'):
            raise ValueError('filter: requires an expression, e.g. map:[students, {grade gt "A"}]')
        return (item for item in seq if predicate.__moyacall__(item))

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

    def parsejson(self, context, v):
        try:
            return moyajson.loads(v)
        except:
            return None

    def get(self, context, v):
        try:
            return connectivity.get(v)
        except:
            return None

    # def group(self, context, v, _get=ExpressionModifiersBase._lookup_key):
    #     seq, key = v
    #     result = OrderedDict()
    #     for item in seq:
    #         k = _get(item, key)
    #         result.setdefault(k, []).append(item)
    #     return result

    def group(self, context, v, _get=ExpressionModifiersBase._lookup_key):
        try:
            seq, key = v
        except ValueError:
            raise ValueError('group: modifier expects [<sequence>, <expression]')
        result = OrderedDict()
        if hasattr(key, '__moyacall__'):
            for item in seq:
                k = key.__moyacall__(item)
                result.setdefault(k, []).append(item)
        else:
            for item in seq:
                k = _get(item, key)
                result.setdefault(k, []).append(item)

        return result

    def counts(self, context, v, _get=ExpressionModifiersBase._lookup_key):
        try:
            seq, key = v
        except ValueError:
            raise ValueError('counts: modifier expects [<sequence>, <expression]')

        if hasattr(key, '__moyacall__'):
            counts = collections.Counter(
                key.__moyacall__(item)
                for item in seq
            )
        else:
            counts = collections.Counter(
                _get(item, key)
                for item in seq
            )
        return counts

    def groupsof(self, context, v):
        try:
            seq, group_size = v
        except:
            raise ValueError('groupsof: operator requires pair of [<sequence>, <group size>')
        seq = list(seq)
        try:
            group_size = int(group_size)
        except:
            raise ValueError("group size must be an integer (not '{}')".format(context.to_expr(group_size)))
        if group_size <= 0:
            raise ValueError("group size must be a positive integer")

        # TODO: Return a generator rather than a list
        grouped = [
            seq[i: i + group_size]
            for i in range(0, len(seq), group_size)
        ]
        return grouped

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
            return [item.id for item in v if hasattr(item, 'id')]
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

    def joinspace(self, context, v):
        return ' '.join(text_type(i) for i in v if i)

    def joinwith(self, context, v):
        try:
            join, char = v
        except:
            raise ValueError("joinwith: expects two values, e.g, joinwith:[filenames, ', ']")
        return text_type(char).join(join)

    def keys(self, context, v):
        return self._keys(context, v)

    def last(self, context, v):
        try:
            return v[-1]
        except IndexError:
            return None

    def len(self, context, v):
        return len(v)

    def linebreaks(self, context, v):
        return HTML(linebreaks(v))

    def list(self, context, v):
        try:
            return list(v)
        except Exception:
            return []

    def localize(self, context, v):
        return self.moya_localize(context, v)

    def log10(self, context, v):
        return log(float(v), 10)

    def lower(self, context, v):
        return text_type(v).lower()

    def lstrip(self, context, v):
        return text_type(v).lstrip()

    def map(self, context, v):
        try:
            seq, key = v
        except ValueError:
            raise ValueError('map: modifier expects [<seq>, <expression>]')
        if not hasattr(key, '__moyacall__'):
            raise ValueError('map: requires an expression, e.g. map:[sequence, {name}]')
        return (key.__moyacall__(item) for item in seq)

    def max(self, context, v):
        return max(_item for _item in v if _item is not None)

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
        return min(_item for _item in v if _item is not None)

    def missing(self, context, v):
        return getattr(v, 'moya_missing', False)

    def none(self, context, v):
        if not v:
            return None
        return v

    def partition(self, context, v, _as_text=as_text):
        split_on = ' '
        if isinstance(v, list):
            try:
                split_on = _as_text(v[1])
                v = _as_text(v[0])
            except IndexError:
                raise ValueError('partition expects string or [<string>, <partition>]')
        else:
            v = _as_text(v)
        a, b, c = v.partition(split_on)
        return a, b, c

    def parsedatetime(self, context, v):
        try:
            date_string, _format = v
        except ValueError:
            raise ValueError('parsedatetime: modifier requires [<datestring>, <dateformat>]')
        return ExpressionDateTime.parse(date_string, _format)

    def replace(self, context, v):
        try:
            text, replace_map = v
        except ValueError:
            raise ValueError('replace: expects [<text>, <replace dict>]')
        replace_map = dict(replace_map)
        text = text_type(text)
        replacer = MultiReplace(replace_map)
        return replacer(text)

    def rpartition(self, context, v, _as_text=as_text):
        split_on = ' '
        if isinstance(v, list):
            try:
                split_on = _as_text(v[1])
                v = _as_text(v[0])
            except IndexError:
                raise ValueError('rpartition expects string or [<string>, <partition>]')
        else:
            v = _as_text(v)
        a, b, c = v.rpartition(split_on)
        return a, b, c

    def path(self, context, v):
        return Path(v)

    def slashjoin(self, context, v):
        return _slashjoin(v)

    def permission(self, context, v):
        return self._permission(context, v)

    def prettyjson(self, context, v):
        return moyajson.dumps(v,
                              sort_keys=True,
                              indent=4,
                              separators=(',', ': '))

    def prettylist(self, context, v):
        return ", ".join("'{}'".format(text_type(s)) for s in v)

    def qsupdate(self, context, v):
        return self._qsupdate(context, v)

    def quote(self, context, v):
        return '"{}"'.format(text_type(v))

    def relto(self, context, v):
        base = dirname(context.get('.request.path', '/'))
        return relativefrom(base, text_type(v))

    def render(self, context, v):
        archive = context['.app.archive']
        if archive is None:
            return text_type(v)
        html = render_object(v, archive, context, 'html')
        return html

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

    def rsorted(self, context, v):
        return sorted(v, reverse=True)

    def rsortedby(self, context, v):
        try:
            seq, key = v[0], v[1]
        except:
            raise ValueError('rsortedby: requires two arguments [<sequence>, <key>]')
        if hasattr(key, '__moyacall__'):
            return sorted(seq, key=key.__moyacall__, reverse=True)
        else:
            return sorted(seq, key=lambda value: obj_index(value, key), reverse=True)

    def round(self, context, v):
        try:
            n, r = v
        except:
            n = v
            r = 0.0
        n = float(n)
        r = int(r)
        return round(n, r)

    def rstrip(self, context, v):
        return text_type(v).rstrip()

    def safe(self, context, v):
        return Safe(v)

    def sentinel(self, context, v):
        name = slugify(text_type(v))
        return Sentinel(name)

    def seqlast(self, context, v):
        return self._seqlast(v, context)

    def set(self, context, v):
        return set(v)

    # Candidate for deprecation
    def slice(self, context, v):
        return slice(*v)

    def slug(self, context, v):
        return slugify(v)

    def sorted(self, context, v):
        return sorted(v)

    def sortedby(self, context, v):
        try:
            seq, key = v[0], v[1]
        except:
            raise ValueError('sortedby: requires two arguments [<sequence>, <key>]')
        if hasattr(key, '__moyacall__'):
            return sorted(seq, key=key.__moyacall__)
        else:
            return sorted(seq, key=lambda value: obj_index(value, key))

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
            return ''

    def splitlast(self, context, v):
        try:
            return self.split(context, v)[-1]
        except IndexError:
            return ''

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

    def stripall(self, context, v):
        try:
            return [text_type(item).strip() for item in v]
        except TypeError:
            raise ValueError('stripall: takes a sequence of strings')

    def striptags(self, context, v):
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

    def trailingslash(self, context, v):
        p = text_type(v)
        if p.endswith('/'):
            return p
        else:
            return p + '/'

    # Candidate for deprecation
    def trim(self, context, v):
        try:
            v, maxlength = v
        except:
            raise ValueError('trim: requires a collection of [<string>, <max length>]')

        s = text_type(v)

        try:
            maxlength = int(maxlength)
        except:
            maxlength = None

        if maxlength is None:
            return v
        return s[:maxlength]

    def ctime(self, context, v):
        return ExpressionDateTime.from_ctime(v)

    def timespan(self, context, v):
        return TimeSpan(v)

    def title(self, context, v):
        return text_type(v).title().replace('_', ' ')

    def token(self, context, v):
        try:
            size = int(v)
        except:
            raise ValueError('token: modifier requires an integer')
        if size < 1:
            raise ValueError('token: modifer requires a size >= 1')
        return ''.join(random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(size))

    def json(self, context, v):
        return moyajson.dumps(v)

    def type(self, context, v):
        return type(v)

    def unique(self, context, v):
        return unique(v)

    def upper(self, context, v):
        return text_type(v).upper()

    def url(self, context, v):
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

    def urlunquote(self, context, v):
        return compat.unquote(text_type(v))

    def urlquote(self, context, v):
        return compat.quote(text_type(v))

    def uuid(self, context, v):
        if v in (1, 4):
            return make_uuid(context, v)
        else:
            try:
                if len(v) == 2:
                    version, nsname = v
                    nstype = 'url'
                elif len(v) == 3:
                    version, nstype, nsname = v
                else:
                    raise ValueError('uuid: modifier requires 1-3 values')
            except (TypeError, ValueError):
                raise ValueError('invalid params for uuid: modifier')
            if version not in (3, 5):
                raise ValueError('uuid: modifier uuid type must be 1, 2, 4, or 5')
            return make_uuid(context, version, nstype=nstype, nsname=py2bytes(nsname))

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
        return list(zip(*v))
