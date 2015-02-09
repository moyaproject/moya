from __future__ import unicode_literals

from .archive import Archive


def get_callable_from_document(path, element_ref, fs='./', breakpoint=False):
    """Shortcut to get a callable from a moya xml document"""
    callable = Archive.get_callable_from_document(path,
                                                  element_ref,
                                                  fs=fs,
                                                  default_context=True,
                                                  breakpoint=breakpoint)
    return callable


def run(path, element_ref, fs='./', breakpoint=False):
    """Run a callable element in a moya xml document"""
    callable = Archive.get_callable_from_document(path,
                                                  element_ref,
                                                  fs=fs,
                                                  default_context=True,
                                                  breakpoint=breakpoint)
    return callable()
