from __future__ import print_function
from __future__ import unicode_literals

import random
import string
import logging

from webob import Request

log = logging.getLogger('moya.asgi')


class ChannelLayer(object):

    def __init__(self, expiry=60, group_expiry=86400):
        self.expiry = expiry
        self.group_expiry = group_expiry

    extensions = []

    class MessageTooLarge(Exception):
        pass

    def send(self, channel, message):
        log.info("send %s -> %s", channel, message)
        if channel == 'http.request':
            Request()

    def receive_many(self, channels, block=False):
        log.info("receive_many %r", channels)
        return None, None

    def new_channel(self, pattern):
        log.info("new_channel %s", pattern)
        new_name = "".join(random.choice(string.ascii_letters) for i in range(8))
        return new_name


channels = ChannelLayer()
