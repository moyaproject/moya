from __future__ import unicode_literals
from ..compat import implements_to_string


@implements_to_string
class DataElement(object):
    def __init__(self, element, context):
        self.libid = element.libid
        self.ns = element.xmlns
        self.tag = element._tag_name
        self.data = element.get_all_data_parameters(context).copy()
        self.children = [DataElement(child, context) for child in element.children()]

    def __str__(self):
        return "<data {}>" .format(self.libid)

    def __repr__(self):
        return "<data {}>" .format(self.libid)
