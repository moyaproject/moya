"""

A color context object

"""


from __future__ import unicode_literals
from __future__ import division
from __future__ import print_function

from moya.compat import text_type, implements_to_string

import re

@implements_to_string
class Color(object):
    """HTML color object"""

    _re_hex = re.compile(r'^\#([a-fA-F0-9]{2})([a-fA-F0-9]{2})([a-fA-F0-9]{2})$')
    _re_rgb = re.compile(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')
    _re_rgba = re.compile(r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9\.]+)\s*\)')

    def __init__(self, r, g, b, a=1.0):
        self._r = float(r)
        self._g = float(g)
        self._b = float(b)
        self._a = float(a)

    def copy(self):
        return Color(self._r, self._g, self._b, self._a)

    @classmethod
    def construct(cls, obj, context):
        if isinstance(obj, cls):
            return obj.copy()
        if isinstance(obj, text_type):
            obj = obj.strip()
            if obj.startswith('#'):
                return cls.parse_hex(obj)
            elif obj.startswith('rgb'):
                return cls.parse_rgb(obj)
            elif obj.startswith('rgba'):
                return cls.parse_rgba(obj)
            else:
                raise ValueError("unable to parse '{}' as a color".format(obj))
        try:
            r, g, b, a = obj
        except:
            pass
        else:
            return cls(r, g, b, a)

        try:
            r, g, b = obj
        except:
            pass
        else:
            return cls(r, g, b)

        raise ValueError("unable to convert {} to a color".format(context.to_expr(obj)))


    @classmethod
    def parse_hex(cls, hex):
        match = cls._re_hex.match(hex)
        if match is None:
            raise ValueError('not valid hex color')
        r, g, b = [int(c, 16) for c in match.groups()]
        return cls(r, g, b)

    @classmethod
    def parse_rgb(cls, rgb):
        match = cls._re_rgb.match(rgb)
        if match is None:
            raise ValueError('not a valid rgb color')
        r, g, b = [int(c) for c in match.groups()]
        return cls(r, g, b)

    @classmethod
    def parse_rgba(cls, rgba):
        match = cls._re_rgba.match(rgba)
        if match is None:
            raise ValueError('not a valid rgb color')
        r, g, b = [int(c) for c in match.groups()[:3]]
        a = float(match.groups()[3])
        return cls(r, g, b, a)


    def __str__(self):
        return self.html

    def __repr__(self):
        return "Color({!r}, {!r}, {!r}, {!r})".format(self, rgba)

    def __moyarepr__(self, context):
        return "color:'{}'".format(self.html)

    @property
    def html(self):
        if self.a == 1:
            return self.hex
        else:
            return self.rgba

    @property
    def hex(self):
        return "#{:02X}{:02X}{:02X}".format(*self._rgb)

    @property
    def rgba(self):
        return "rgba({},{},{},{:g})".format(*self._rgba)

    @property
    def _rgb(self):
        return [int(self.r), int(self.g), int(self.b)]

    @property
    def _rgba(self):
        return [int(self.r), int(self.g), int(self.b), self.a]

    def _get_r(self):
        return min(255.0, max(0.0, self._r))
    def _set_r(self, r):
        self._r = float(r)
    r = property(_get_r, _set_r)

    def _get_g(self):
        return min(255.0, max(0.0, self._g))
    def _set_g(self, g):
        self._g = float(g)
    g = property(_get_g, _set_g)

    def _get_b(self):
        return min(255.0, max(0.0, self._b))
    def _set_b(self, b):
        self._b = float(b)
    b = property(_get_b, _set_b)

    def _get_a(self):
        return min(1.0, max(0.0, self._a))
    def _set_a(self, a):
        self._a = float(a)
    a = property(_get_a, _set_a)


if __name__ == "__main__":
    print(unicode(Color(20, 255, 0)))
    print(unicode(Color(20, 255, 0, 0.5)))

    print(unicode(Color.parse_hex('#00FF34').html))

    print(unicode(Color.parse_rgb('rgb(100, 23,50)').html))

    print(unicode(Color.parse_rgba('rgba(100, 23,50, 0.6)').html))
