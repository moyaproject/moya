from __future__ import unicode_literals

__author__ = "Will McGugan <admin@moyaproject.com>"
__version__ = "0.5.13a"
# *** Don't forget to update version in setup.py ***

__all__ = ['pilot', 'expose']


from . import expose
from .moyapilot import Pilot
from .compat import text_type


pilot = Pilot()

import decimal

decimal.Decimal.__moyarepr__ = lambda self, context: "d:'{}'".format(text_type(self))
