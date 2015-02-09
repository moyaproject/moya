"""A base 64 encoding to pack PKs"""

from __future__ import unicode_literals

import moya

alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"


@moya.expose.filter('encode_id')
def pack(i):
    letters = ''
    while i:
        letters += alphabet[i % 64]
        i //= 64
    return letters


@moya.expose.filter('decode_id')
def unpack(s):
    i = 0
    for c in reversed(s):
        i = i * 64 + alphabet.index(c)
    return i
