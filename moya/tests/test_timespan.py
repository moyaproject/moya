import unittest

from moya.context.expressiontime import TimeSpan


class TestTimeSpan(unittest.TestCase):

    def test_create(self):
        """Test creating timespans"""
        for ts, ms, s, m, h, d in [(TimeSpan(10), 10, 0, 0, 0, 0),
                                   (TimeSpan('10ms'), 10, 0, 0, 0, 0),
                                   (TimeSpan('10s'), 10 * 1000, 10, 0, 0, 0),
                                   (TimeSpan('2m'), 2 * 1000 * 60, 2 * 60, 2, 0, 0),
                                   (TimeSpan('3h'), 3 * 1000 * 60 * 60, 3 * 60 * 60, 3 * 60, 3, 0),
                                   (TimeSpan('5d'), 5 * 1000 * 60 * 60 * 24, 5 * 60 * 60 * 24, 5 * 60 * 24, 5 * 24, 5),
                                   (TimeSpan('1h 30m'), 90 * 1000 * 60, 90 * 60, 90, 1, 0),
                                ]:
            self.assertEqual(int(ts), ms)
            self.assertEqual(ts.milliseconds, ms)
            self.assertEqual(ts.seconds, s)
            self.assertEqual(ts.hours, h)
            self.assertEqual(ts.hours, h)
            self.assertEqual(ts.days, d)

    def test_math(self):
        """Test mathematical operations"""
        self.assertEqual(TimeSpan('10'), TimeSpan('10ms'))
        self.assertEqual(TimeSpan(10), TimeSpan('10ms'))
        self.assertEqual(TimeSpan('1h') + TimeSpan('30m'), TimeSpan('90m'))
        self.assertEqual(TimeSpan('1h') - TimeSpan('15m'), TimeSpan('45m'))
        self.assertEqual(TimeSpan('1h') * 3, TimeSpan('3h'))
        self.assertEqual(TimeSpan('60m') * 24, TimeSpan('1d'))
        self.assertEqual(TimeSpan('1h') - TimeSpan('1m'), TimeSpan('59m'))
        self.assertEqual(TimeSpan('1h 30m 10s'), TimeSpan('90m 10000ms'))
        self.assert_(TimeSpan('30m') == TimeSpan('30m'))
        self.assert_(TimeSpan('30m') != TimeSpan('30h'))
        self.assert_(TimeSpan('1m'))
        self.assert_(not TimeSpan())
        self.assert_(not TimeSpan('0'))
        self.assert_(not (TimeSpan('1h') - TimeSpan('60m')))
