from __future__ import unicode_literals


class BoundElement(object):

    __slots__ = ('app', 'element')

    def __init__(self, app, element):
        self.app = app
        self.element = element

    @classmethod
    def from_tuple(cls, app_element):
        app, element = app_element
        return cls(app, element)

    def __repr__(self):
        return "<{1} in app {0}>".format(self.app, self.element)

    def __iter__(self):
        return iter(('app', 'element'))

    def __getitem__(self, key):
        if key == 'app':
            return self.app
        elif key == 'element':
            return self.element
        raise KeyError(key)

    def __moyamodel__(self):
        return self.app, self.element

    def keys(self):
        return ('app', 'element')

    def iterkeys(self):
        return iter(self.keys())

    def values(self):
        return (self.app, self.element)

    def itervalues(self):
        return iter(self.values())

    def items(self):
        return [('app', self.app), ('element', self.element)]

    def iteritems(self):
        return self.items()
