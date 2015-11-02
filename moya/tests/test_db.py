from __future__ import unicode_literals
from __future__ import print_function

import unittest

from moya.build import build_server
from moya import db

import os
from os.path import dirname, join, abspath

curdir = dirname(abspath(__file__))

from moya.console import Console
from moya import pilot


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

        #build_result = build_server(join(curdir, 'dbtest/'), "settings.ini")
        self.archive = build_result.archive
        self.base_context = build_result.context

        self.context = self.base_context.clone()
        archive.populate_context(self.context)

        root = self.context.root
        root['_dbsessions'] = db.get_session_map(self.archive)

    def tearDown(self):
        try:
            os.remove("dbtest.sqlite")
        except OSError as e:
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

    def test_owner(self):
        """Test object ownership"""
        context = self.context
        call = self.archive.call
        with pilot.manage(context):
            call("dbtest#owner_test", context, None)
            owner = call("dbtest#get_owner", context, None, name="owner")
            print(owner)
            self.assertEqual(owner.name, 'owner')

            child1 = call("dbtest#get_child", context, None, name="child1")
            child2 = call("dbtest#get_child", context, None, name="child2")
            child3 = call("dbtest#get_child", context, None, name="child3")
            child4 = call("dbtest#get_child", context, None, name="child4")

            print(child1, child2, child3, child4)
            assert child1, "child1 should exist"
            assert child2, "child2 should exist"
            assert child3, "child3 should exist"
            assert child4, "child4 should exist"
            assert owner.unowned_child is child1
            assert owner.owned_child is child2
            assert owner.unowned_child_o2o is child3
            assert owner.owned_child_o2o is child4

            call("dbtest#delete_owner", context, None, name="owner")
            print(owner)
            owner = call("dbtest#get_owner", context, None, name="owner")

            print(owner)
            assert not owner, "owner is {}".format(owner)

            child1 = call("dbtest#get_child", context, None, name="child1")
            child2 = call("dbtest#get_child", context, None, name="child2")
            child3 = call("dbtest#get_child", context, None, name="child1")
            child4 = call("dbtest#get_child", context, None, name="child2")

            print(child1, child2, child3, child4)
            assert child1, "child1 should exists"
            assert not child2, "child2 should not exists"
            assert child3, "child3 should exists"
            assert not child4, "child4 should not exists"

    def test_owned(self):
        """Test owned objects"""

        context = self.context
        call = self.archive.call
        with pilot.manage(context):
            call('dbtest#make_post', context, None)

            post = call('dbtest#get_post', context, None, name="post")
            assert post.name == 'post', "post should be called 'post'"
            assert post.images[0].name == 'images1', 'expected images1'

            images = call('dbtest#get_images', context, None, name="images1")
            assert images.name == 'images1', "images should be named 'images1'"

            call('dbtest#delete_post', context, None, name="post")

            images = call('dbtest#get_images', context, None, name="images1")
            assert not images, "images should have been deleted"
