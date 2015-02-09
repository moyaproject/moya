from __future__ import unicode_literals

__all__ = ["attr_bool"]


def attr_bool(s):
    """Converts an attribute in to a boolean

    A True value is returned if the string matches 'y', 'yes' or 'true'.
    The comparison is case-insensitive and whitespace is stripped.
    All other values are considered False. If None is passed in, then None will be returned.

    """
    if s is None or isinstance(s, bool):
        return s
    return s.strip().lower() in ('yes', 'true')
