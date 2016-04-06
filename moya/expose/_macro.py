from __future__ import print_function
from __future__ import unicode_literals

from ._exposed import exposed_elements


def macro(libname):
    """Decorator for macros (Moya callables)."""
    def deco(f):
        exposed_elements[libname] = f
        return f
    return deco
