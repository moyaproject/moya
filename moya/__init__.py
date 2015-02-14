from __future__ import unicode_literals

__author__ = "Will McGugan <admin@moyaproject.com>"
__version__ = "0.5.0"
# *** Don't forget to update version in setup.py ***

__all__ = ['pilot', 'expose']


from . import expose
from .moyapilot import Pilot
from .compat import text_type


pilot = Pilot()

import decimal


class MoyaDecimal(decimal.Decimal):

    def __moyarepr__(self, context):
        return "d:'{}'".format(text_type(self))


decimal.Decimal = MoyaDecimal
