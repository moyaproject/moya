from __future__ import unicode_literals
from ..interface import AttributeExposer


class ElementProxy(AttributeExposer):
    __moya_exposed_attributes__ = ["app", "tag", "params", "element_ref", "tag_name"]

    def __init__(self, context, app, element):
        self.app = app
        self.tag = element
        self.params = element.get_all_parameters(context)
        self.element_ref = "{}#{}".format(app.name if app else element.lib.long_name, element.libname)
        self.tag_name = element._tag_name

    def __moyaelement__(self):
        return self.tag

    def __repr__(self):
        return "<element {}>".format(self.element_ref)

    def __moyaconsole__(self, context, console):
        obj_params = dict(app=self.app,
                          tag_name=self.tag_name,
                          tag=self.tag,
                          params=self.params,
                          element_ref=self.element_ref)
        console.obj(context, obj_params)


class DataElementProxy(AttributeExposer):
    __moya_exposed_attributes__ = ["app",
                                   "tag",
                                   "params",
                                   "element_ref",
                                   "tag_name",
                                   "data"]

    def __init__(self, context, app, element, data):
        self.app = app
        self.tag = element
        self.params = element.get_all_parameters(context)
        self.element_ref = "{}#{}".format(app.name if app else element.lib.long_name, element.libname)
        self.tag_name = element._tag_name
        self.data = data

    def __moyaelement__(self):
        return self.tag

    def __repr__(self):
        return "<element {}>".format(self.element_ref)

    def __moyaconsole__(self, context, console):
        obj_params = dict(app=self.app,
                          tag_name=self.tag_name,
                          tag=self.tag,
                          params=self.params,
                          element_ref=self.element_ref,
                          data=self.data)
        console.obj(context, obj_params)
