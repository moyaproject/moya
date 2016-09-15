from __future__ import unicode_literals
from __future__ import print_function

import pytz
from .context.expressiontime import ExpressionDateTime
from .compat import implements_to_string, text_type, string_types

from tzlocal import get_localzone

common_timezones = pytz.common_timezones


def _make_choice(t):
    return t, t.replace('_', ' ').replace('/', ' / ')

common_timezones_choices = [_make_choice(t) for t in common_timezones]


def get_common_timezones_groups():
    regions = []
    region_map = {}
    for tz in common_timezones:
        if '/' in tz:
            region, label = tz.split('/', 1)
        else:
            region = ''
            label = tz
        if region not in region_map:
            regions.append(region)
            region_map[region] = []
        region_map[region].append((tz, label.replace('_', ' ').replace('/', ' / ')))
    regions.sort()
    return [(r, region_map[r]) for r in regions]


def write_common_timezones(path):
    from json import dump
    import io
    with io.open(path, 'wb') as f:
        dump(get_common_timezones_groups(), f)


@implements_to_string
class Timezone(object):
    def __init__(self, tz="UTC"):
        if isinstance(tz, Timezone):
            self.tz = tz.tz
        else:
            if tz == 'auto':
                self.tz = get_localzone()
            else:
                self.tz = pytz.timezone(tz or "UTC")

    def __str__(self):
        return text_type(self.tz.zone)

    def __repr__(self):
        return '<timezone "{}">'.format(self.tz.zone)

    def __moyafilter__(self, context, app, dt, params):
        if isinstance(dt, string_types):
            dt = ExpressionDateTime.from_isoformat(dt)
        return self(dt)

    def __call__(self, dt):
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        return dt.astimezone(self.tz)


if __name__ == "__main__":

    from datetime import datetime

    t = datetime.utcnow()

    tz = Timezone("Asia/Seoul")

    print(repr(tz))
    print(text_type(tz))

    print(tz(t))
