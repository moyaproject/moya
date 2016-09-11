from __future__ import unicode_literals
from ..interface import AttributeExposer

import weakref


class ElementProxy(AttributeExposer):
    __moya_exposed_attributes__ = ["app",
                                   "tag",
                                   "params",
                                   "attributes",
                                   "element_ref",
                                   "tag_name",
                                   "tag_xmlns",
                                   "tag_type",
                                   "parent"]

    def __init__(self, context, app, element):
        self._context = weakref.ref(context)
        self.app = app
        self.tag = element
        self.attributes = element.get_all_parameters(context)
        self.element_ref = "{}#{}".format(app.name if app else element.lib.long_name, element.libname)
        self.tag_name = element._tag_name
        self.tag_xmlns = element.xmlns
        self.tag_type = "{{{}}}{}".format(self.tag_xmlns, self.tag_name)

    @property
    def context(self):
        return self._context()

    @property
    def params(self):
        return self.attributes

    @property
    def parent(self):
        if not self.tag.parent:
            return None
        return ElementProxy(self.context, self.app, self.tag.parent)

    def __moyaelement__(self):
        return self.tag

    def __repr__(self):
        return "<element {}>".format(self.element_ref)

    def __moyaconsole__(self, context, console):
        obj_params = dict(app=self.app,
                          tag_name=self.tag_name,
                          tag=self.tag,
                          atributes=self.attributes,
                          element_ref=self.element_ref)
        console.obj(context, obj_params)

    def qualify(self, app):
        self.app = app
        self.element_ref = "{}#{}".format(app.name if app else element.lib.long_name, element.libname)

class DataElementProxy(AttributeExposer):
    __moya_exposed_attributes__ = ["app",
                                   "tag",
                                   "params",
                                   "attributes",
                                   "element_ref",
                                   "tag_name",
                                   "tag_xmlns",
                                   "tag_type",
                                   "data",
                                   "parent"]

    def __init__(self, context, app, element, data):
        self.app = app
        self.tag = element
        self.attributes = element.get_all_parameters(context)
        self.element_ref = "{}#{}".format(app.name if app else element.lib.long_name, element.libname)
        self.tag_name = element._tag_name
        self.data = data
        self.tag_xmlns = element.xmlns
        self.tag_type = "{{{}}}{}".format(self.tag_xmlns, self.tag_name)

    @property
    def params(self):
        return self.attributes

    def __moyaelement__(self):
        return self.tag

    def __repr__(self):
        return "<element {}>".format(self.element_ref)

    def __moyaconsole__(self, context, console):
        obj_params = dict(app=self.app,
                          tag_name=self.tag_name,
                          tag=self.tag,
                          attributes=self.attributes,
                          element_ref=self.element_ref,
                          data=self.data)
        console.obj(context, obj_params)
