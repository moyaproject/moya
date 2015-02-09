from __future__ import unicode_literals
from __future__ import print_function

from ..context.tools import to_expression
from ..compat import (number_types,
                      implements_to_string,
                      xrange,
                      implements_bool,
                      string_types,
                      unichr)

__all__ = ["ExpressionRange",
           "ExclusiveIntegerRange",
           "InclusiveIntegerRange",
           "ExclusiveCharacterRange",
           "InclusiveCharacterRange"]


@implements_bool
@implements_to_string
class ExpressionRange(object):
    inclusive = True

    @classmethod
    def create(cls, context, start, end, inclusive=True):
        if not isinstance(start, number_types + string_types):
            if hasattr(start, '__moyarange__'):
                moyarange = start.__moyarange__(context, end, inclusive=inclusive)
            else:
                raise ValueError("Can't create range from {!r} to {!r}".format(start, end))
            return moyarange
        if isinstance(start, number_types):
            if inclusive:
                return InclusiveIntegerRange(context, start, end)
            else:
                return ExclusiveIntegerRange(context, start, end)
        elif isinstance(start, string_types):
            if inclusive:
                return InclusiveCharacterRange(context, start, end)
            else:
                return ExclusiveCharacterRange(context, start, end)
        raise ValueError("Can't create range from {} to {}".format(to_expression(context, start),
                                                                   to_expression(context, end)))

    def __init__(self, context, start, end):
        self.start = start
        self.end = end
        try:
            self._build(start, end)
        except TypeError:
            raise ValueError("Can't create range between {} and {}".format(to_expression(context, start),
                                                                           to_expression(context, end)))

    def __str__(self):
        return "<range {} to {} inclusive>".format(self.start, self.end)

    def _build(self, start, end):
        raise NotImplementedError

    # def __moyaconsole__(self, console):
    #     return console.text(unicode(self))

    def __moyarepr__(self, context):
        if self.inclusive:
            return "({})..({})".format(to_expression(context, self.start),
                                       to_expression(context, self.end))
        else:
            return "({})...({})".format(to_expression(context, self.start),
                                        to_expression(context, self.end))

    def keys(self):
        return range(0, len(self))

    def values(self):
        return list(self)

    def items(self):
        return list(enumerate(self))

    def __bool__(self):
        return bool(len(self))

    def __add__(self, value):
        return list(self) + [value]

    def __radd__(self, value):
        return [value] + list(self)

    def __sub__(self, value):
        l = list(self)
        l.remove(value)
        return l

    def __getitem__(self, index):
        try:
            index = int(index)
        except TypeError:
            raise
        for i, v in enumerate(self):
            if i == index:
                return v
        raise KeyError(index)

    def __contains__(self, value):
        return any(v == value for v in self)

    def __len__(self):
        return sum(1 for _ in self)


@implements_to_string
class ExclusiveIntegerRange(ExpressionRange):
    inclusive = False

    def _build(self, start, end):
        self._a = int(start)
        self._b = int(end)
        self._forward = end >= start

    def __str__(self):
        return "<range {} to {} exclusive>".format(self.start, self.end)

    def __iter__(self):
        if self._forward:
            return iter(xrange(self._a, self._b))
        else:
            return iter(xrange(self._a, self._b, -1))

    def __contains__(self, v):
        try:
            v = int(v)
        except TypeError:
            return False
        if self._forward:
            return v >= self._a and v < self._b
        else:
            return v <= self._a and v > self._b

    def __len__(self):
        return abs(self._a - self._b)


@implements_to_string
class InclusiveIntegerRange(ExpressionRange):
    inclusive = True

    def _build(self, start, end):
        self._a = int(start)
        self._b = int(end)
        self._forward = end >= start

    def __str__(self):
        return "<range {} to {} inclusive>".format(self.start, self.end)

    def __iter__(self):
        if self._forward:
            return iter(xrange(self._a, self._b + 1))
        else:
            return iter(xrange(self._a, self._b - 1, -1))

    def __contains__(self, v):
        try:
            v = int(v)
        except TypeError:
            return False
        if self._forward:
            return v >= self._a and v <= self._b
        else:
            return v <= self._a and v >= self._b

    def __len__(self):
        return abs(self._a - self._b) + 1


@implements_to_string
class ExclusiveCharacterRange(ExpressionRange):
    inclusive = False

    def _build(self, start, end):
        self._a = ord(start[0])
        self._b = ord(end[0])
        self._forward = end >= start

    def __str__(self):
        return "<range {} to {} exclusive>".format(self.start, self.end)

    def __iter__(self):
        if self._forward:
            return iter(unichr(c) for c in xrange(self._a, self._b))
        else:
            return iter(unichr(c) for c in xrange(self._a, self._b, -1))

    def __contains__(self, v):
        if not isinstance(v, string_types):
            return False
        if len(v) != 1:
            return False
        v = ord(v[0])
        if self._forward:
            return v >= self._a and v < self._b
        else:
            return v <= self._a and v > self._b

    def __len__(self):
        return abs(self._a - self._b)


@implements_to_string
class InclusiveCharacterRange(ExpressionRange):
    invlusive = True

    def _build(self, start, end):
        self._a = ord(start[0])
        self._b = ord(end[0])
        self._forward = end >= start

    def __str__(self):
        return "<range {} to {} inclusive>".format(self.start, self.end)

    def __iter__(self):
        if self._forward:
            return iter(unichr(c) for c in xrange(self._a, self._b + 1))
        else:
            return iter(unichr(c) for c in xrange(self._a, self._b - 1, -1))

    def __contains__(self, v):
        if not isinstance(v, string_types):
            return False
        if len(v) != 1:
            return False
        v = ord(v[0])
        if self._forward:
            return v >= self._a and v <= self._b
        else:
            return v >= self._b and v <= self._a

    def __len__(self):
        return abs(self._a - self._b) + 1


if __name__ == "__main__":
    r = ExpressionRange.create(0.0, 10, inclusive=False)
    print(len(r))
    print(list(r))
