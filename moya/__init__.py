from __future__ import unicode_literals

__author__ = "Will McGugan <admin@moyaproject.com>"
__version__ = "0.5.16"
# *** Don't forget to update version in setup.py ***

__all__ = ['pilot', 'expose']


from . import expose
from .moyapilot import Pilot
from .compat import text_type, PY2


pilot = Pilot()

import decimal

if PY2:
    decimal.Decimal.__moyarepr__ = lambda self, context: "d:'{}'".format(text_type(self))
    _decimal_str = decimal.Decimal.__str__
    decimal.Decimal.__str__ = lambda self: "{:f}".format(self.normalize())
    decimal.Decimal.__unicode__ = decimal.Decimal.__str__

else:
    _decimal_normalize = decimal.Decimal.normalize

    class MoyaDecimal(decimal.Decimal):

        def __moyarepr__(self, context):
            return "d:'{}'".format(self.normalize())

        def __str__(self):
            return "{:f}".format(self.normalize())

        def __unicode__(self):
            return "{:f}".format(self.normalize())

    decimal.Decimal = MoyaDecimal
