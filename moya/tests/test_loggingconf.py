from __future__ import unicode_literals

from moya import loggingconf

from fs.osfs import OSFS

import os.path
from os.path import join


class TestLoggingConf(object):

    def setUp(self):
        self.path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'loggingconf')
        print(self.path)

    def tearDown(self):
        pass

    def test_init(self):
        """Test reading logging conf"""
        loggingconf.init_logging(join(self.path, 'logging.ini'))
        loggingconf.init_logging(join(self.path, 'extend.ini'))

    def test_fs(self):
        """test reading logging from fs"""
        fs = OSFS(self.path)
        loggingconf.init_logging_fs(fs, 'logging.ini')
        loggingconf.init_logging_fs(fs, 'extend.ini')
