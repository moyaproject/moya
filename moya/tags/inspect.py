from __future__ import unicode_literals


from ..tags.context import DataSetter
from .. import errors


class ElementContainer(object):

    def __init__(self, archive):
        self.archive = archive

    def __getitem__(self, elementid):
        return self.archive.get_element(elementid)

    def __contains__(self, elementid):
        try:
            self[elementid]
        except errors.ElementNotFoundError:
            return False
        else:
            return True


class Inspect(DataSetter):
    """
    Get an object which contains all the elements in the project.
    """

    class Help:
        synopsis = "inspect elements in the project"

    def get_value(self, context):
        return ElementContainer(self.archive)
