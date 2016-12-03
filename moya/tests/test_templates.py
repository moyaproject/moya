from __future__ import unicode_literals

import unittest
import os
import time
from os.path import join

from fs.opener import open_fs
from moya.template.moyatemplates import MoyaTemplateEngine
from moya.archive import Archive
from moya.settings import SettingsContainer


class TestTemplates(unittest.TestCase):
    def setUp(self):
        path = os.path.abspath(os.path.dirname(__file__))
        templates_path = join(path, "templates")
        self.fs = open_fs(templates_path)
        self.archive = Archive()
        self.archive.init_cache("templates", SettingsContainer.create(type="dict"))
        self.archive.init_cache("fragment", SettingsContainer.create(type="dict"))
        self.engine = MoyaTemplateEngine(self.archive, self.fs, {})

    def tearDown(self):
        self.fs.close()
        self.fs = None
        self.archive = None
        self.engine = None

    def _render(self, *template_paths, **kwargs):
        return self.engine.render(template_paths, kwargs)

    def test_substitute(self):
        """Test template substitution"""
        tests = [
            (dict(fruit="apple"), "My favorite fruit is apple"),
            (dict(fruit="pear"), "My favorite fruit is pear"),
            (dict(), "My favorite fruit is ")
        ]
        for test_data, result in tests:
            html = self._render("simplesub.html", **test_data)
            self.assertEqual(result, html)

    def test_safe_substitute(self):
        """Test safe strings"""
        from moya.render import HTML
        html = self._render("simplesub.html", fruit="<em>oranges</em>")
        self.assertEqual(html, "My favorite fruit is &lt;em&gt;oranges&lt;/em&gt;")

        html = self._render("simplesub.html", fruit=HTML("<em>oranges</em>"))
        self.assertEqual(html, "My favorite fruit is <em>oranges</em>")

    def test_if(self):
        """Test template IF tag"""
        tests = [
            (dict(fruit="apple"), "I like apples"),
            (dict(fruit="pear"), "Pears are good"),
            (dict(), "I don't like fruit")
        ]
        for test_data, result in tests:
            html = self._render("if.html", **test_data)
            self.assertEqual(result, html)

    def test_for(self):
        """Test template FOR tag"""
        fruits = ["apples", "oranges", "carrot", "pears"]
        tests = [
            (dict(fruits=fruits), "I like apples, oranges, pears"),
            (dict(fruits=[]), "I don't like fruit"),
        ]
        for test_data, result in tests:
            html = self._render("for.html", **test_data)
            self.assertEqual(result, html)

    def test_escape(self):
        """Test HTML escaping"""
        tests = [
            (dict(text="Stuff & things"), "Stuff &amp; things"),
            (dict(text="<html>"), "&lt;html&gt;"),
        ]
        for test_data, result in tests:
            html = self._render("escape.html", **test_data)
            self.assertEqual(result, html)

    def test_extends(self):
        """Test extending templates"""
        html = self._render("extends.html", title="Hello")
        self.assertEqual(html, "<title>Hello</title>")

    def test_block(self):
        """Test extending templates"""
        html = self._render("extendsreplace.html")
        self.assertEqual(html, "B\n")
        html = self._render("extendsreplaceexplicit.html")
        self.assertEqual(html, "B\n")
        html = self._render("extendsappend.html")
        self.assertEqual(html, "A\nB\n")
        html = self._render("extendsprepend.html")
        self.assertEqual(html, "B\nA\n")

    def test_def(self):
        """Test def and call tags in templates"""
        html = self._render("def.html", fruit="apples")
        self.assertEqual("I like apples", html)

    def test_emit(self):
        """Test emit tag in template"""
        html = self._render("emit.html")
        self.assertEqual(html, "{% ${nosubstitute} %}")

    def test_comments(self):
        """Test template comments"""
        html = self._render("comment.html")
        self.assertEqual(html, "apples")
        html = self._render("comment2.html")
        self.assertEqual(html.splitlines()[0].rstrip(), "0 1  3")

    def test_empty(self):
        """Test empty template"""
        html = self._render("empty.html")
        self.assertEqual(html, "")

    def test_justtext(self):
        """Test plain text template"""
        html = self._render("justtext.html")
        self.assertEqual(html, "Just\nText")

    def test_verbatim(self):
        """Test verbatim tag"""
        html = self._render("verbatim.html")
        self.assertEqual("{% for fruit in fruits %}${fruit}{% endfor %}", html)

    def test_cache(self):
        """Test cache tag"""
        html = self._render("cache.html")
        result_html = "<ul><li>1</li><li>2</li><li>3</li></ul>"
        self.assertEqual(html, result_html)
        # A second time so it is read from the cache
        html = self._render("cache.html")
        result_html = "<ul><li>1</li><li>2</li><li>3</li></ul>"
        self.assertEqual(html, result_html)
        # Sleep so the key expires
        time.sleep(.1)
        # Check it once more
        html = self._render("cache.html")
        result_html = "<ul><li>1</li><li>2</li><li>3</li></ul>"
        self.assertEqual(html, result_html)

    def test_whitespace(self):
        """Test syntax for whitespace removal"""
        html = self._render("whitespace.html")
        self.assertEqual(html, "12345")
