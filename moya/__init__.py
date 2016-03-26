from __future__ import unicode_literals

import decimal

from . import expose
from .compat import text_type, PY2
from .moyapilot import Pilot
from ._version import VERSION as __version__


__author__ = "Will McGugan <admin@moyaproject.com>"
__all__ = ['pilot', 'expose']


pilot = Pilot()

if PY2:

    decimal.Decimal.__moyarepr__ = lambda self, context: "d:'{}'".format(text_type(self))
    _decimal_str = decimal.Decimal.__str__
    decimal.Decimal.__str__ = lambda self: "{:f}".format(self.normalize())
    decimal.Decimal.__unicode__ = decimal.Decimal.__str__


else:
    _decimal_normalize = decimal.Decimal.normalize

    class MoyaDecimal(decimal.Decimal):

        def __moyarepr__(self, context):
            return "d:'{}'".format(_decimal_normalize(self))

        def __str__(self):
            return "{:f}".format(_decimal_normalize(self))

        def __unicode__(self):
            return "{:f}".format(_decimal_normalize(self))

    decimal.Decimal = MoyaDecimal
