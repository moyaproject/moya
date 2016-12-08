from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from ..compat import implements_to_string, text_type, string_types, number_types, implements_bool

from ..interface import AttributeExposer
from .. import interface
from ..tools import parse_timedelta
from .. import pilot
from ..context.expressionrange import ExpressionRange

from datetime import date, time, datetime, timedelta
from calendar import monthrange, timegm
from math import floor
import re
import iso8601
from babel.dates import (format_datetime,
                         format_date,
                         format_time,
                         format_timedelta,
                         parse_pattern)

import calendar
from pytz import UTC, timezone


utcfromtimestamp = datetime.utcfromtimestamp
utclocalize = UTC.localize
GMT = timezone('GMT')


def datetime_to_epoch(d):
    """Convert datetime to epoch"""
    return timegm(d.utctimetuple())


def epoch_to_datetime(t):
    """Convert epoch time to a UTC datetime"""
    return utclocalize(utcfromtimestamp(t))


class DatetimeExclusiveRange(ExpressionRange):

    def _build(self, start, end):
        self.start = start
        self.end = end
        self.step = timedelta(days=1)
        self._forward = end >= start

    def __iter__(self):
        if self._forward:
            d = self.start
            while d < self.end:
                yield d
                d += self.step
        else:
            d = self.start
            while d > self.end:
                yield d
                d -= self.step

    def __moyacall__(self, params):
        step = params.get('step', None)
        if step is not None:
            self.step = timedelta(milliseconds=step)
        return self

    def __contains__(self, v):
        if self._forward:
            return v >= self.start and v < self.stop
        else:
            return v <= self.start and v > self.stop


class DatetimeInclusiveRange(DatetimeExclusiveRange):

    def __iter__(self):
        if self._forward:
            d = self.start
            while d <= self.end:
                yield d
                d += self.step
        else:
            d = self.start
            while d >= self.end:
                yield d
                d -= self.step


class ExpressionDate(date, interface.Proxy):

    @classmethod
    def from_sequence(self, seq):
        try:
            year, month, day = (int(s) for s in seq)
        except ValueError:
            raise ValueError('[year, month, day] should be integers')
        except:
            raise ValueError('[year, month, day] required')
        return ExpressionDate(year, month, day).moya_proxy

    @classmethod
    def from_date(self, d):
        return ExpressionDate(d.year, d.month, d.day).moya_proxy

    @classmethod
    def from_isoformat(cls, s):
        if isinstance(s, date):
            return cls.from_date(s)
        if isinstance(s, ExpressionDateTime):
            return s.date
        try:
            dt = iso8601.parse_date(s)
            return cls.from_date(dt.date())
        except:
            return None

    def __moyadbobject__(self):
        return date(self.year,
                    self.month,
                    self.day)

    @implements_to_string
    class ProxyInterface(AttributeExposer):
        __moya_exposed_attributes__ = ["year", "month", "day",
                                       "next_month", "previous_month",
                                       "isoformat", "next_day", "previous_day",
                                       "leap"]

        def __init__(self, obj):
            self.date = obj

        def __hash__(self):
            return hash(interface.unproxy(self))

        def __moyapy__(self):
            return self.date

        def __moyajson__(self):
            return self.isoformat

        def __format__(self, fmt):
            return format(self.date, fmt)

        def __str__(self):
            return self.isoformat

        def __repr__(self):
            return '<date "{}">'.format(self.isoformat)

        def __moyarepr__(self, context):
            return "date:'{}'".format(self.isoformat)

        def __moyalocalize__(self, context, locale):
            fmt = context.get('.sys.site.date_format', 'medium')
            return format_date(self.date, format=fmt, locale=text_type(locale))

        def __moyarange__(self, context, end, inclusive=False):
            if inclusive:
                return DatetimeInclusiveRange(context, self, end)
            else:
                return DatetimeExclusiveRange(context, self, end)

        def __moyaconsole__(self, console):
            console(self.isoformat).nl()

        def __mod__(self, fmt):
            return format_date(self.date,
                               format=fmt,
                               locale=text_type(pilot.context.get('.locale', 'en_US')))

        @property
        def year(self):
            return self.date.year

        @property
        def month(self):
            return self.date.month

        @property
        def day(self):
            return self.date.day

        @property
        def isoformat(self):
            return self.date.isoformat()

        @property
        def next_day(self):
            return ExpressionDate.from_date(self.date + timedelta(days=1))

        @property
        def previous_day(self):
            return ExpressionDate.from_date(self.date + timedelta(days=-1))

        @property
        def next_month(self):
            """The first date in the following month"""
            d = self.date
            if d.month == 12:
                return ExpressionDate(d.year + 1, 1,)
            else:
                return ExpressionDate(d.year, d.month + 1, 1)

        @property
        def previous_month(self):
            """First date in the previous month"""
            d = self.date
            if d.month == 1:
                return ExpressionDate(d.year - 1, 12, 1)
            else:
                return ExpressionDate(d.year, d.month - 1, 1)

        @property
        def leap(self):
            return calendar.isleap(self.year)

        def __sub__(self, other):
            dt = self.date
            other = interface.unproxy(other)
            result = dt - other
            if isinstance(result, date):
                return ExpressionDate.from_date(result)
            elif isinstance(result, (timedelta, TimeSpan)):
                return TimeSpan.from_timedelta(result)
            else:
                return result

        def __add__(self, other):
            dt = self.date
            other = interface.unproxy(other)
            if isinstance(other, time):
                return ExpressionDateTime.combine(self.date, other)
            result = dt + other
            if isinstance(result, date):
                return ExpressionDate.from_date(result)
            elif isinstance(result, (timedelta, TimeSpan)):
                return TimeSpan.from_timedelta(result)
            else:
                return result

        def __eq__(self, other):
            return interface.unproxy(self) == interface.unproxy(other)

        def __ne__(self, other):
            return interface.unproxy(self) != interface.unproxy(other)

        def __lt__(self, other):
            return interface.unproxy(self) < interface.unproxy(other)

        def __le__(self, other):
            return interface.unproxy(self) <= interface.unproxy(other)

        def __gt__(self, other):
            return interface.unproxy(self) > interface.unproxy(other)

        def __ge__(self, other):
            return interface.unproxy(self) >= interface.unproxy(other)


class ExpressionTime(time, interface.Proxy):

    _re_time = re.compile(r'^(\d\d)\:(\d\d)(?:\:(\d{1,2}\.?\d+?))?$')

    @classmethod
    def from_time(self, t):
        return ExpressionTime(t.hour, t.minute, t.second, t.microsecond, t.tzinfo).moya_proxy

    @classmethod
    def from_isoformat(cls, t):
        t = interface.unproxy(t)
        if isinstance(t, time):
            return cls.from_time(t)
        if isinstance(t, ExpressionDateTime):
            return t.time.moya_proxy
        try:
            hour, minute, second = cls._re_time.match(t).groups()
            microsecond = 0

            if '.' in second:
                second, fraction = second.split('.', 1)
                fraction = float(fraction)
                if fraction:
                    microsecond = int((1.0 / fraction) * 1000000)
            time_obj = time(int(hour), int(minute), int(second), int(microsecond))
            return cls.from_time(time_obj)
        except:
            return None

    @implements_to_string
    class ProxyInterface(AttributeExposer):

        __moya_exposed_attributes__ = ["hour", "minute", "second", "microsecond",
                                       "tzinfo",
                                       "isoformat"]

        def __init__(self, obj):
            self.time = obj

        def __hash__(self):
            return hash(interface.unproxy(self))

        def __moyapy__(self):
            return self.time

        def __moyajson__(self):
            return self.isoformat

        def __format__(self, fmt):
            return format(self.time, fmt)

        def __str__(self):
            return self.isoformat

        def __repr__(self):
            return '<time "{}">'.format(self.isoformat)

        def __moyarepr__(self, context):
            return "time:'{}'".format(self.isoformat)

        def __moyalocalize__(self, context, locale):
            fmt = context.get('.sys.site.time_format', 'medium')
            return format_time(self.time, fmt, locale=text_type(locale))

        def __moyaconsole__(self, console):
            console(self.isoformat).nl()

        def __getattr__(self, k):
            if k in self.__moya_exposed_attributes__:
                return getattr(self.time, k)
            raise AttributeError(k)

        def __mod__(self, fmt):
            try:
                return format_time(self.time,
                                   fmt,
                                   locale=text_type(pilot.context.get('.locale', 'en_US')))
            except:
                raise ValueError("'{}' is not a valid time format string".format(fmt))

        @property
        def isoformat(self):
            return self.time.isoformat()

        def __eq__(self, other):
            return interface.unproxy(self) == interface.unproxy(other)

        def __ne__(self, other):
            return interface.unproxy(self) != interface.unproxy(other)

        def __lt__(self, other):
            return interface.unproxy(self) < interface.unproxy(other)

        def __le__(self, other):
            return interface.unproxy(self) <= interface.unproxy(other)

        def __gt__(self, other):
            return interface.unproxy(self) > interface.unproxy(other)

        def __ge__(self, other):
            return interface.unproxy(self) >= interface.unproxy(other)


class ExpressionDateTime(datetime, interface.Proxy):

    @classmethod
    def moya_utcnow(self):
        return self.ProxyInterface.utcnow()

    @classmethod
    def from_datetime(cls, dt):
        return cls.ProxyInterface(dt)

    @classmethod
    def from_isoformat(cls, s):
        if isinstance(s, number_types):
            return cls.from_datetime(datetime.fromtimestamp(s))
        if isinstance(s, datetime):
            return cls.from_datetime(s)
        if isinstance(s, ExpressionDateTime):
            return s
        try:
            dt = iso8601.parse_date(s)
            return cls.from_datetime(dt)
        except:
            #raise
            return None

    @classmethod
    def from_ctime(cls, s):
        try:
            dt = cls.strptime(text_type(s), "%a %b %d %H:%M:%S %Y")
            return cls.from_datetime(dt)
        except:
            return None

    @classmethod
    def from_epoch(cls, epoch):
        return cls.ProxyInterface(epoch_to_datetime(epoch))

    @classmethod
    def parse(cls, t, pattern):
        try:
            dt = datetime.strptime(t, pattern)
            return cls.from_datetime(dt)
        except:
            #raise
            return None

    def __moyarepr__(self, context):
        return "datetime:'{}'".format(self.isoformat())

    def __moyadbobject__(self):
        dt = self.moya_proxy.utc.naive
        dt = datetime(dt.year,
                      dt.month,
                      dt.day,
                      dt.hour,
                      dt.minute,
                      dt.second,
                      dt.microsecond,
                      dt.tzinfo)
        return dt

    @implements_to_string
    class ProxyInterface(AttributeExposer):

        __moya_exposed_attributes__ = ["year", "month", "day", "minute", "hour", "second", "microsecond", "tzinfo",
                                       "date", "time",
                                       "year_start", "month_start", "day_start",
                                       "next_day", "next_year", "next_month",
                                       "previous_day", "previous_month", "previous_year",
                                       'leap',
                                       "days_in_month", "epoch",
                                       "isoformat", "local", 'utc', 'naive',
                                       "html5_datetime", "html5_date", "html5_time",
                                       'rfc2822', 'http_date']

        _re_date = re.compile(r"^(\d\d\d\d)-(\d\d)-(\d\d)$")
        _re_time = re.compile(r'^(\d\d)\:(\d\d)(?:\:(\d{1,2}\.?\d+?))?$')

        def __init__(self, obj):
            self._dt = obj

        def __hash__(self):
            return hash(interface.unproxy(self))

        def __moyarepr__(self, context):
            return "datetime:'{}'".format(self.isoformat)

        def __moyapy__(self):
            return self._dt

        def __moyajson__(self):
            return self.isoformat

        def __moyaconsole__(self, console):
            console.text(text_type(self.ctime()))

        def __moyarange__(self, context, end, inclusive=False):
            if inclusive:
                return DatetimeInclusiveRange(context, self, end)
            else:
                return DatetimeExclusiveRange(context, self, end)

        def __str__(self):
            return self.isoformat

        def __repr__(self):
            return '<datetime "{}">'.format(self.isoformat)

        def __format__(self, fmt):
            return format(self._dt, fmt)

        def __moyalocalize__(self, context, locale):
            fmt = context.get('.sys.site.datetime_format', 'medium')
            return format_datetime(self.local._dt, format=fmt, locale=text_type(locale))

        def __moyadbobject__(self):
            dt = self.utc.naive
            dt = datetime(dt.year,
                          dt.month,
                          dt.day,
                          dt.hour,
                          dt.minute,
                          dt.second,
                          dt.microsecond,
                          dt.tzinfo)
            return dt

        def __getattr__(self, key):
            return getattr(self._dt, key)

        @classmethod
        def utcnow(cls):
            now = ExpressionDateTime.from_datetime(datetime.utcnow())
            return now

        @classmethod
        def from_datetime(cls, dt):
            return ExpressionDateTime.from_datetime(dt)

        @classmethod
        def make(cls, *args, **kwargs):
            return cls(datetime(*args, **kwargs))

        @classmethod
        def from_html5(cls, s):
            if isinstance(s, datetime):
                return cls.from_datetime(s)
            if isinstance(s, ExpressionDateTime):
                return s
            s = text_type(s)
            if 'T' in s:
                date_s, time_s = s.split('T', 1)
            else:
                date_s = s
                time_s = "00:00"
            try:
                year, month, day = cls._re_date.match(date_s).groups()
                hour, minute, second = cls._re_time.match(time_s).groups()
            except AttributeError:
                raise ValueError("Could not parse '{}' as a html5 date/time".format(s))

            second = float(second or 0.0)
            microsecond = int(floor(second * 1000000) % 1000000)

            return ExpressionDateTime(int(year),
                                      int(month),
                                      int(day),
                                      int(hour),
                                      int(minute),
                                      int(second),
                                      int(microsecond))

        @property
        def date(self):
            dt = self._dt
            return ExpressionDate(dt.year, dt.month, dt.day)

        @property
        def time(self):
            dt = self._dt
            return ExpressionTime(dt.hour, dt.minute, dt.second, dt.microsecond, dt.tzinfo)

        @property
        def year_start(self):
            """Start of the year"""
            dt = self._dt
            return ExpressionDateTime(dt.year, 1, 1, tzinfo=dt.tzinfo)

        @property
        def month_start(self):
            """Start of the month"""
            dt = self._dt
            return ExpressionDateTime(dt.year, dt.month, 1, tzinfo=dt.tzinfo)

        @property
        def day_start(self):
            """Start of the day"""
            dt = self._dt
            return ExpressionDateTime(dt.year, dt.month, dt.day, tzinfo=dt.tzinfo)

        @property
        def next_year(self):
            """First date in the following year"""
            dt = self._dt
            return ExpressionDateTime(dt.year + 1, 1, 1, tzinfo=dt.tzinfo)

        @property
        def next_month(self):
            """The first date in the following month"""
            dt = self._dt
            if dt.month == 12:
                return ExpressionDateTime(dt.year + 1, 1, 1, tzinfo=dt.tzinfo)
            else:
                return ExpressionDateTime(dt.year, dt.month + 1, 1, tzinfo=dt.tzinfo)

        @property
        def next_day(self):
            """The start of the following day"""
            return self.from_datetime(self._dt + timedelta(hours=24)).day_start

        @property
        def previous_day(self):
            return self.from_datetime(self._dt - timedelta(hours=24)).day_start

        @property
        def previous_year(self):
            """First date in the previous year"""
            dt = self._dt
            return ExpressionDateTime(dt.year - 1, 1, 1, tzinfo=dt.tzinfo)

        @property
        def previous_month(self):
            """First date in the previous month"""
            dt = self._dt
            if dt.month == 1:
                return ExpressionDateTime(dt.year - 1, 12, 1, tzinfo=dt.tzinfo)
            else:
                return ExpressionDateTime(dt.year, dt.month - 1, 1, tzinfo=dt.tzinfo)

        @property
        def leap(self):
            return calendar.isleap(self.date.year)

        @property
        def days_in_month(self):
            dt = self._dt
            _, maxdays = monthrange(dt.year, dt.month)
            return maxdays

        @property
        def epoch(self):
            return datetime_to_epoch(self._dt)

        @property
        def html5_datetime(self):
            return "{}T{}".format(self.html5_date,
                                  self.html5_time)

        @property
        def html5_date(self):
            dt = self._dt
            fmt = "{:04}-{:02}-{:02}"
            return fmt.format(dt.year,
                              dt.month,
                              dt.day)

        @property
        def html5_time(self):
            dt = self._dt
            fmt = "{:02}:{:02}"
            return fmt.format(dt.hour,
                              dt.minute)

        @property
        def isoformat(self):
            dt = self._dt
            return datetime.isoformat(dt)

        @property
        def rfc2822(self):
            from email import utils
            return utils.formatdate(self.epoch)

        @property
        def http_date(self):
            dt = self._dt
            gmt_time = GMT.localize(dt)
            return gmt_time.strftime('%a, %d %b %Y %H:%M:%S GMT')

        @property
        def utc(self):
            dt = self._dt
            if dt.tzinfo is None:
                return self.from_datetime(UTC.localize(dt))
            return self.from_datetime(dt.astimezone(UTC))

        @property
        def naive(self):
            dt = self._dt
            return self.make(dt.year,
                             dt.month,
                             dt.day,
                             dt.hour,
                             dt.minute,
                             dt.second,
                             dt.microsecond)

        @property
        def local(self):
            tz = pilot.context.get('.tz', None)
            if tz is None:
                return None
            return self.from_datetime(tz(self._dt))

        def __mod__(self, fmt):
            self = self._dt
            return format_datetime(self,
                                   fmt,
                                   locale=text_type(pilot.context.get('.locale', 'en_US')))

        def __sub__(self, other):
            dt = self._dt
            result = dt - interface.unproxy(other)
            if isinstance(result, datetime):
                return ExpressionDateTime.from_datetime(result)
            elif isinstance(result, (timedelta, TimeSpan)):
                return TimeSpan.from_timedelta(result)
            else:
                return result

        def __add__(self, other):
            dt = self._dt
            result = dt + interface.unproxy(other)
            if isinstance(result, datetime):
                return ExpressionDateTime.from_datetime(result)
            elif isinstance(result, (timedelta, TimeSpan)):
                return TimeSpan.from_timedelta(result)
            else:
                return result

        def __eq__(self, other):
            return interface.unproxy(self) == interface.unproxy(other)

        def __ne__(self, other):
            return interface.unproxy(self) != interface.unproxy(other)

        def __lt__(self, other):
            return interface.unproxy(self) < interface.unproxy(other)

        def __le__(self, other):
            return interface.unproxy(self) <= interface.unproxy(other)

        def __gt__(self, other):
            return interface.unproxy(self) > interface.unproxy(other)

        def __ge__(self, other):
            return interface.unproxy(self) >= interface.unproxy(other)


def to_milliseconds(value):
    if isinstance(value, TimeSpan):
        return int(TimeSpan(value).milliseconds)
    else:
        return int(value) if value is not None else None


def to_seconds(value):
    if isinstance(value, TimeSpan):
        return int(TimeSpan(value).seconds)
    else:
        return int(value) if value is not None else None


@implements_bool
@implements_to_string
class TimeSpan(object):
    def __init__(self, ms=0):
        if isinstance(ms, string_types):
            self._ms = float(sum(parse_timedelta(token)
                             for token in ms.split()))
        else:
            self._ms = float(ms)

    def __str__(self):
        return self.text

    def __repr__(self):
        return "TimeSpan('%s')" % self.simplify

    def __moyarepr__(self, context):
        return self.simplify

    # def __moyaconsole__(self, console):
    #     console(self.text).nl()

    @classmethod
    def from_timedelta(cls, time_delta):
        if isinstance(time_delta, TimeSpan):
            return TimeSpan(time_delta._ms)
        return TimeSpan(time_delta.total_seconds() * 1000.0)

    @classmethod
    def to_ms(cls, value):
        if isinstance(value, string_types):
            return parse_timedelta(value)
        else:
            return int(value)

    @property
    def simplify(self):
        """Units in lowest common denominator"""
        ms = self._ms
        for unit, divisible in [('d', 1000 * 60 * 60 * 24),
                                ('h', 1000 * 60 * 60),
                                ('m', 1000 * 60),
                                ('s', 1000),
                                ('ms', 1)]:
            if not (ms % divisible):
                return "{}{}".format(ms // divisible, unit)

    def __moyalocalize__(self, context, locale):
        fmt = context.get('.sys.site.timespan_format', 'medium')
        td = timedelta(milliseconds=self._ms)
        return format_timedelta(td, format=fmt, locale=text_type(locale))

    @property
    def text(self):
        """Nice textual representation of a time span"""
        ms = self._ms
        text = []
        for name, plural, divisable in [("day", "days", 1000 * 60 * 60 * 24),
                                        ("hour", "hours", 1000 * 60 * 60),
                                        ("minute", "minutes", 1000 * 60),
                                        ("second", "seconds", 1000),
                                        ("millisecond", "milliseconds", 1)]:
            unit = ms // divisable
            if unit:
                if unit == 1:
                    text.append("%i %s" % (unit, name))
                else:
                    text.append("%i %s" % (unit, plural))
            ms -= (unit * divisable)
        if not text:
            return "0 seconds"
        else:
            return ", ".join(text)

    @property
    def milliseconds(self):
        return self._ms

    @property
    def seconds(self):
        return self._ms // 1000

    @property
    def minutes(self):
        return self._ms // (1000 * 60)

    @property
    def hours(self):
        return self._ms // (1000 * 60 * 60)

    @property
    def days(self):
        return self._ms // (1000 * 60 * 60 * 24)

    def __int__(self):
        return int(self._ms)

    def __float__(self):
        return float(self._ms / 1000.0)

    def __bool__(self):
        return bool(self._ms)

    def __add__(self, other):
        if isinstance(other, datetime):
            return ExpressionDateTime.from_datetime(other + timedelta(milliseconds=self._ms))
        elif isinstance(other, date):
            return ExpressionDate.from_date(other + timedelta(milliseconds=self._ms))
        return TimeSpan(self._ms + self.to_ms(other))

    def __sub__(self, other):
        if isinstance(other, datetime):
            return ExpressionDateTime.from_datetime(other - timedelta(milliseconds=self._ms))
        return TimeSpan(self._ms - self.to_ms(other))

    def __mul__(self, other):
        return TimeSpan(self._ms * float(other))

    def __eq__(self, other):
        return self._ms == self.to_ms(other)

    def __rmul__(self, other):
        return TimeSpan(self._ms * float(other))

    def __radd__(self, other):
        if isinstance(other, datetime):
            return ExpressionDateTime.from_datetime(other + timedelta(milliseconds=self._ms))
        elif isinstance(other, date):
            return ExpressionDate.from_date(other + timedelta(milliseconds=self._ms))
        else:
            return self + self.to_ms(other)

    def __rsub__(self, other):
        if isinstance(other, datetime):
            return ExpressionDateTime.from_datetime(other - timedelta(milliseconds=self._ms))
        elif isinstance(other, date):
            return ExpressionDate.from_date(other - timedelta(milliseconds=self._ms))
        else:
            return self - self.to_ms(other)

    def __neg__(self):
        return TimeSpan(-self._ms)

    def __pos__(self):
        return TimeSpan(+self._ms)

    def __abs__(self):
        return TimeSpan(abs(self._ms))

    def __ne__(self, other):
        return self._ms != self.to_ms(other)

    def __lt__(self, other):
        return self._ms < self.to_ms(other)

    def __le__(self, other):
        return self._ms <= self.to_ms(other)

    def __gt__(self, other):
        return self._ms > self.to_ms(other)

    def __ge__(self, other):
        return self._ms >= self.to_ms(other)


if __name__ == "__main__":
    n = ExpressionDateTime.now()
    print(n.isoformat)

    d = n.isoformat.replace('T', ' ')
    print(ExpressionDateTime.from_isoformat(d).isoformat)

    # print n
    # print n + "1h"
    # print n - "1d"
