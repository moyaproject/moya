from __future__ import unicode_literals
from __future__ import print_function

from .compat import implements_to_string, itervalues
from itertools import chain

import weakref


@implements_to_string
class FilterKeyError(KeyError):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg

    def __repr__(self):
        return "FilterKeyError({!r})".format(self.msg)


@implements_to_string
class FilterContainer(object):
    """Collection that exposes a unified interface to filters"""

    def __init__(self, archive):
        self._archive = weakref.ref(archive)

    def __repr__(self):
        return "<filters>"

    def __str__(self):
        return "<filters>"

    @property
    def archive(self):
        return self._archive()

    def _lookup(self, app, name):
        if app is not None:
            if name in app.filters:
                return [app.filters[name]]
        if ' ' in name:
            tokens = name.split()
            if len(tokens) != 3 or tokens[1] != 'from':
                raise ValueError('filter strings should be in the format "<NAME> from <APP or LIB>"')
            name, _, app_name = tokens
            apps = [self.archive.find_app(app_name)]
        else:
            apps = self.archive.apps.values()

        filters = [filter_app.filters[name] for filter_app in apps if name in filter_app.filters]
        return filters

    def lookup(self, app, name):
        if app is not None:
            if name in app.filters:
                return app.filters[name]
        if ' ' in name:
            tokens = name.split()
            if len(tokens) != 3 or tokens[1] != 'from':
                raise ValueError('filter strings should be in the format "<NAME> from <APP or LIB>"')
            name, _, app_name = tokens
            apps = [self.archive.find_app(app_name)]
        else:
            apps = self.archive.apps.values()

        filters = [filter_app.filters[name] for filter_app in apps if name in filter_app.filters]
        if not filters:
            raise FilterKeyError("no filter called '{}'".format(name))
        if len(filters) != 1:
            raise ValueError('filter is ambiguous, specify "{} from <APP or LIB>"'.format(name))
        return filters[0]

    def __getitem__(self, name):
        f = self._lookup(None, name)
        if not f:
            raise FilterKeyError(name)
        if len(f) == 1:
            return f[0]
        return f

    def __contains__(self, name):
        if ' ' in name:
            name = name.split(' ', 1)[0]
        return any(name in app.filters for app in itervalues(self.archive.apps))

    def __iter__(self):
        return iter(self.keys())

    def __len__(self):
        return len(set(chain.from_iterable(app.filters.keys() for app in itervalues(self.archive.apps))))

    def keys(self):
        return sorted(set(chain.from_iterable(app.filters.keys() for app in itervalues(self.archive.apps))))

    def values(self):
        return [self._lookup(None, name) for name in self.keys()]

    def items(self):
        return zip(self.keys(), self.values())

    def as_dict(self):
        return dict(self.items())
