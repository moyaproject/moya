from __future__ import unicode_literals

from moya import expose


@expose.macro("macro.expose.double")
def double(n):
    return n * 2

@expose.macro("macro.expose.tripple")
def tripple(n):
    return n * 3

@expose.filter('cube')
def cube(n):
    return n**3
