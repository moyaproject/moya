from __future__ import unicode_literals

from moya.expose import View


class TestView(View):
    name = "hello"

    def get(self, context):
        return "Hello, World"
