from __future__ import unicode_literals
from __future__ import print_function

import unittest

from moya.build import build_server
from moya import db

import os
from os.path import dirname, join, abspath

curdir = dirname(abspath(__file__))

from moya.console import Console


class TestDB(unittest.TestCase):

    def setUp(self):

        try:
            os.remove("dbtest.sqlite")
        except OSError:
            pass

        build_result = build_server(join(curdir, 'dbtest/'), "settings.ini")
        archive = build_result.archive
        base_context = build_result.context

        archive.populate_context(build_result.context)
        console = Console()
        db.sync_all(build_result.archive, console)

        context = base_context.clone()
        root = context.root
        root['_dbsessions'] = db.get_session_map(archive)
        archive.call("dbtest#setup", context, None, id=1)
        db.commit_sessions(context)

        build_result = build_server(join(curdir, 'dbtest/'), "settings.ini")
        self.archive = build_result.archive
        self.base_context = build_result.context

        self.context = self.base_context.clone()
        archive.populate_context(self.context)

        root = self.context.root
        root[u'_dbsessions'] = db.get_session_map(self.archive)

    def tearDown(self):
        try:
            os.remove("dbtest.sqlite")
        except OSError:
            pass

    def test_bulk_create(self):
        """Test bulk create of db"""
        context = self.context
        print(context.root.keys())
        obj = self.archive.call("dbtest#get_by_id", context, None, id=1)
        self.assertEqual(obj.id, 1)

        obj = self.archive.call("dbtest#get_by_id", context, None, id=2)

        self.assertEqual(obj.id, 2)
        obj = self.archive.call("dbtest#get_by_title", context, None, title="Zen 2")
        self.assertEqual(obj.id, 2)
