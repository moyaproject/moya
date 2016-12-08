import unittest

from moya.context import Context
from moya.context.expressiontime import ExpressionDateTime
from moya.compat import text_type
from moya import pilot
from moya.timezone import Timezone


class TestExpressionTime(unittest.TestCase):

    def setUp(self):
        self.context = Context()
        root = self.context.root
        root['now'] = ExpressionDateTime.utcnow()
        root['tz'] = Timezone('UTC')

    def test_str(self):
        text_type(self.context['.now'])

    def test_keys_values(self):
        with pilot.manage(self.context):
            self.context.eval('keys:.now')
            self.context.eval('values:.now')
            self.context.eval('items:.now')
