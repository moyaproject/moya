"""
Various functions to interface templates with moya

"""
from __future__ import unicode_literals
from ..compat import string_types


class Interface(object):

    def __init__(self, archive, context):
        self.archive = archive
        self.context = context
        self.urls = context['.urls']
        self.settings = self.archive.settings

    def render(self, obj, target='html'):
        if isinstance(obj, string_types):
            return obj
        if hasattr(obj, 'moya_render'):
            if hasattr(obj, 'moya_render_targets') and target not in obj.moya_render_targets:
                return ''
            return obj.moya_render(self.archive, self.context, target=target)
