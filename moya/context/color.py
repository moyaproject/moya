"""

A color context object

"""


from __future__ import unicode_literals
from __future__ import division
from __future__ import print_function

from ..compat import text_type, implements_to_string
from ..interface import AttributeExposer

from collections import OrderedDict
import colorsys
import re

# Borrowed from https://github.com/bahamas10/css-color-names/blob/master/css-color-names.json
HTML_COLORS = {
    "aqua": "#00ffff",
    "aliceblue": "#f0f8ff",
    "antiquewhite": "#faebd7",
    "black": "#000000",
    "blue": "#0000ff",
    "cyan": "#00ffff",
    "darkblue": "#00008b",
    "darkcyan": "#008b8b",
    "darkgreen": "#006400",
    "darkturquoise": "#00ced1",
    "deepskyblue": "#00bfff",
    "green": "#008000",
    "lime": "#00ff00",
    "mediumblue": "#0000cd",
    "mediumspringgreen": "#00fa9a",
    "navy": "#000080",
    "springgreen": "#00ff7f",
    "teal": "#008080",
    "midnightblue": "#191970",
    "dodgerblue": "#1e90ff",
    "lightseagreen": "#20b2aa",
    "forestgreen": "#228b22",
    "seagreen": "#2e8b57",
    "darkslategray": "#2f4f4f",
    "darkslategrey": "#2f4f4f",
    "limegreen": "#32cd32",
    "mediumseagreen": "#3cb371",
    "turquoise": "#40e0d0",
    "royalblue": "#4169e1",
    "steelblue": "#4682b4",
    "darkslateblue": "#483d8b",
    "mediumturquoise": "#48d1cc",
    "indigo": "#4b0082",
    "darkolivegreen": "#556b2f",
    "cadetblue": "#5f9ea0",
    "cornflowerblue": "#6495ed",
    "mediumaquamarine": "#66cdaa",
    "dimgray": "#696969",
    "dimgrey": "#696969",
    "slateblue": "#6a5acd",
    "olivedrab": "#6b8e23",
    "slategray": "#708090",
    "slategrey": "#708090",
    "lightslategray": "#778899",
    "lightslategrey": "#778899",
    "mediumslateblue": "#7b68ee",
    "lawngreen": "#7cfc00",
    "aquamarine": "#7fffd4",
    "chartreuse": "#7fff00",
    "gray": "#808080",
    "grey": "#808080",
    "maroon": "#800000",
    "olive": "#808000",
    "purple": "#800080",
    "lightskyblue": "#87cefa",
    "skyblue": "#87ceeb",
    "blueviolet": "#8a2be2",
    "darkmagenta": "#8b008b",
    "darkred": "#8b0000",
    "saddlebrown": "#8b4513",
    "darkseagreen": "#8fbc8f",
    "lightgreen": "#90ee90",
    "mediumpurple": "#9370db",
    "darkviolet": "#9400d3",
    "palegreen": "#98fb98",
    "darkorchid": "#9932cc",
    "yellowgreen": "#9acd32",
    "sienna": "#a0522d",
    "brown": "#a52a2a",
    "darkgray": "#a9a9a9",
    "darkgrey": "#a9a9a9",
    "greenyellow": "#adff2f",
    "lightblue": "#add8e6",
    "paleturquoise": "#afeeee",
    "lightsteelblue": "#b0c4de",
    "powderblue": "#b0e0e6",
    "firebrick": "#b22222",
    "darkgoldenrod": "#b8860b",
    "mediumorchid": "#ba55d3",
    "rosybrown": "#bc8f8f",
    "darkkhaki": "#bdb76b",
    "silver": "#c0c0c0",
    "mediumvioletred": "#c71585",
    "indianred": "#cd5c5c",
    "peru": "#cd853f",
    "chocolate": "#d2691e",
    "tan": "#d2b48c",
    "lightgray": "#d3d3d3",
    "lightgrey": "#d3d3d3",
    "thistle": "#d8bfd8",
    "goldenrod": "#daa520",
    "orchid": "#da70d6",
    "palevioletred": "#db7093",
    "crimson": "#dc143c",
    "gainsboro": "#dcdcdc",
    "plum": "#dda0dd",
    "burlywood": "#deb887",
    "lightcyan": "#e0ffff",
    "lavender": "#e6e6fa",
    "darksalmon": "#e9967a",
    "palegoldenrod": "#eee8aa",
    "violet": "#ee82ee",
    "azure": "#f0ffff",
    "honeydew": "#f0fff0",
    "khaki": "#f0e68c",
    "lightcoral": "#f08080",
    "sandybrown": "#f4a460",
    "beige": "#f5f5dc",
    "mintcream": "#f5fffa",
    "wheat": "#f5deb3",
    "whitesmoke": "#f5f5f5",
    "ghostwhite": "#f8f8ff",
    "lightgoldenrodyellow": "#fafad2",
    "linen": "#faf0e6",
    "salmon": "#fa8072",
    "oldlace": "#fdf5e6",
    "bisque": "#ffe4c4",
    "blanchedalmond": "#ffebcd",
    "coral": "#ff7f50",
    "cornsilk": "#fff8dc",
    "darkorange": "#ff8c00",
    "deeppink": "#ff1493",
    "floralwhite": "#fffaf0",
    "fuchsia": "#ff00ff",
    "gold": "#ffd700",
    "hotpink": "#ff69b4",
    "ivory": "#fffff0",
    "lavenderblush": "#fff0f5",
    "lemonchiffon": "#fffacd",
    "lightpink": "#ffb6c1",
    "lightsalmon": "#ffa07a",
    "lightyellow": "#ffffe0",
    "magenta": "#ff00ff",
    "mistyrose": "#ffe4e1",
    "moccasin": "#ffe4b5",
    "navajowhite": "#ffdead",
    "orange": "#ffa500",
    "orangered": "#ff4500",
    "papayawhip": "#ffefd5",
    "peachpuff": "#ffdab9",
    "pink": "#ffc0cb",
    "red": "#ff0000",
    "seashell": "#fff5ee",
    "snow": "#fffafa",
    "tomato": "#ff6347",
    "white": "#ffffff",
    "yellow": "#ffff00",
    "rebeccapurple": "#663399"
}

# Add 'special' colors
HTML_COLORS['transparent'] = "rgba(0,0,0,0)"


@implements_to_string
class Color(AttributeExposer):
    """HTML color object"""

    __moya_exposed_attributes__ = [
        "r", "g", "b", "a",
        "rgb", "rgba", "hsl", "hsla",
        "html", "hex",
        "name",
        "opaque", "saturated"
    ]

    _re_hex = re.compile(r'^\#([a-fA-F0-9]{2})([a-fA-F0-9]{2})([a-fA-F0-9]{2})$')
    _re_hex_short = re.compile(r'^\#([a-fA-F0-9]{1})([a-fA-F0-9]{1})([a-fA-F0-9]{1})$')
    _re_rgb = re.compile(r'rgb\(\s*([0-9\.]+)\s*,\s*([0-9\.]+)\s*,\s*([0-9\.]+)\s*\)')
    _re_rgba = re.compile(r'rgba\(\s*([0-9\.]+)\s*,\s*([0-9\.]+)\s*,\s*([0-9\.]+)\s*,\s*([0-9\.]+)\s*\)')
    _re_hsl = re.compile(r'hsl\(\s*([0-9\.]+)\s*,\s*([0-9\.]+)\%\s*,\s*([0-9\.]+)\%\s*\)')
    _re_hsla = re.compile(r'hsla\(\s*([0-9\.]+)\s*,\s*([0-9\.]+)\%\s*,\s*([0-9\.]+)\%\s*,\s*([0-9\.]+)\s*\)')

    def __init__(self, r, g, b, a=1.0):
        self._r = float(r)
        self._g = float(g)
        self._b = float(b)
        self._a = float(a)

    def copy(self):
        return Color(self._r, self._g, self._b, self._a)

    @classmethod
    def construct(cls, context, obj):
        if isinstance(obj, cls):
            return obj.copy()
        if isinstance(obj, text_type):
            return cls.parse(obj)
        if isinstance(obj, (float, int)):
            return cls(obj, obj, obj)

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
    def parse(cls, txt):
        txt = txt.strip().lower()
        if txt == 'inherit':
            return 'inherit'
        if txt in HTML_COLORS:
            return HTML_COLORS[txt]
        elif txt.startswith('#'):
            return cls.parse_hex(txt)
        elif txt.startswith('rgba'):
            return cls.parse_rgba(txt)
        elif txt.startswith('rgb'):
            return cls.parse_rgb(txt)
        elif txt.startswith('hsla'):
            return cls.parse_hsla(txt)
        elif txt.startswith('hsl'):
            return cls.parse_hsl(txt)
        else:
            raise ValueError("unable to parse '{}' as a color".format(txt))

    @classmethod
    def parse_hex(cls, hex):
        match = cls._re_hex_short.match(hex)
        if match is not None:
            r, g, b = [int(c + c, 16) for c in match.groups()]
            return cls(r, g, b)
        else:
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

    @classmethod
    def parse_hsl(cls, hsl):
        match = cls._re_hsl.match(hsl)
        if match is None:
            raise ValueError('not a valid hsl color')
        h, s, l = [float(c) for c in match.groups()]
        h = h / 360.0
        l = l / 100.0
        s = s / 100.0
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return cls(r * 255.0, g * 255.0, b * 255.0)

    @classmethod
    def parse_hsla(cls, hsla):
        match = cls._re_hsla.match(hsla)
        if match is None:
            raise ValueError('not a valid hsla color')
        h, s, l, a = [float(c) for c in match.groups()]
        h = h / 360.0
        l = l / 100.0
        s = s / 100.0
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return cls(r * 255.0, g * 255.0, b * 255.0, a * 255.0)

    def __moyaconsole__(self, console):
        from moya import pilot
        link = "http://www.color-hex.com/color/{}".format(self.hex.lower()[1:])
        mr = self.__moyarepr__(pilot.context)
        console.text(mr, bold=True)
        console.text(link, fg="cyan", underline=True)
        # keys = OrderedDict((k, getattr(self, k)) for k in self.__moya_exposed_attributes__)
        # console.obj(pilot.context, keys)

    def __str__(self):
        return self.html

    def __repr__(self):
        return "Color({!r}, {!r}, {!r}, {!r})".format(self._r, self._g, self._b, self._a)

    def __moyarepr__(self, context):
        return "color:[{:g}, {:g}, {:g}, {:g}]".format(self._r, self._g, self._b, self._a)

    def __hash__(self):
        return hash((self._r, self._g, self._b, self._a))

    def as_pillow_tuple(self):
        if self.a == 1.0:
            return (int(self.r), int(self.g), int(self.b))
        else:
            return (int(self.r), int(self.g), int(self.b), int(self.a * 255.0))

    @property
    def html(self):
        if self.a == 1.0:
            return self.hex
        else:
            return self.rgba

    @property
    def hex(self):
        if any(c % 17 for c in self._rgb):
            return "#{:02X}{:02X}{:02X}".format(*self._rgb)
        else:
            return "#{:0X}{:0X}{:0X}".format(*(c // 17 for c in self._rgb))

    @property
    def rgb(self):
        return "rgb({},{},{})".format(*self._rgb)

    @property
    def rgba(self):
        return "rgba({},{},{},{:g})".format(*self._rgba)

    @property
    def hsl(self):
        h, l, s = colorsys.rgb_to_hls(self.r / 255.0, self.g / 255.0, self.b / 255.0)
        return "hsl({:g},{:g}%,{:g}%)".format(h * 360.0, s * 100.0, l * 100.0)

    @property
    def hsla(self):
        h, l, s = colorsys.rgb_to_hls(self.r / 255.0, self.g / 255.0, self.b / 255.0)
        return "hsla({:g},{:g}%,{:g}%,{:g})".format(h * 360.0, s * 100.0, l * 100.0, self.a)

    @property
    def _rgb(self):
        return [int(self.r), int(self.g), int(self.b)]

    @property
    def _rgba(self):
        return [int(self.r), int(self.g), int(self.b), self.a]

    @property
    def opaque(self):
        return Color(self._r, self._g, self._b, 1.0)

    @property
    def saturated(self):
        return Color(self.r, self.g, self.b, self.a)

    @property
    def r(self):
        return min(255.0, max(0.0, self._r))

    @property
    def g(self):
        return min(255.0, max(0.0, self._g))

    @property
    def b(self):
        return min(255.0, max(0.0, self._b))

    @property
    def a(self):
        return min(1.0, max(0.0, self._a))

    @property
    def name(self):
        return HTML_COLORS_REVERSE.get(self, None)

    def __eq__(self, other):
        if not isinstance(other, Color):
            raise ValueError('can only compare a color to another color')
        return self._r == other._r and self._g == other._g and self._b == other._b and self._a == other._a

    def __add__(self, other):
        if not isinstance(other, Color):
            raise ValueError('can only add another color to a color')
        r, g, b, a = self._rgba
        _r, _b, _g, _a = other._rgba
        return Color(r + _r, g + _g, b + _b, a)

    def __sub__(self, other):
        if not isinstance(other, Color):
            raise ValueError('can only subtract another color from a color')
        r, g, b, a = self._rgba
        _r, _b, _g, _a = other._rgba
        return Color(r - _r, g - _g, b - _b, a)

    def __mul__(self, other):
        if isinstance(other, (float, int)):
            r, g, b, a = self._rgba
            return Color(r * other, g * other, b * other, a)
        if not isinstance(other, Color):
            raise ValueError('can only multiple a color by a number or other color')
        r, g, b, a = self._rgba
        _r, _g, _b, _a = other._rgba
        return Color(r * _r, g * _g, b * _b, a)

    def __div__(self, other):
        raise NotImplementedError("can't divide a color")

HTML_COLORS = {k: Color.parse(v) for k, v in HTML_COLORS.items()}
HTML_COLORS_REVERSE = {v: k for k, v in HTML_COLORS.items()}


if __name__ == "__main__":
    print(unicode(Color(20, 255, 0)))
    print(unicode(Color(20, 255, 0, 0.5)))

    print(unicode(Color.parse_hex('#00FF34').html))

    print(unicode(Color.parse_rgb('rgb(100, 23,50)').html))

    print(unicode(Color.parse_rgba('rgba(100, 23,50, 0.6)').html))

    print(Color.parse('tomato'))
    print(Color.parse('white'))

    print(Color.parse('hsl(200, 50%, 10%)'))
    print(Color.parse('hsla(200, 50%, 10%, 0.5)'))

    print(Color.parse('hsl(120, 100%, 50%)'))
