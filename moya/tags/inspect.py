from __future__ import unicode_literals


from ..tags.context import DataSetter
from ..elements import Attribute
from .. import errors
from moya.compat import text_type


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


class QualifyElementref(DataSetter):
    """
    Qualifies an element reference.

    """

    app = Attribute("An application name", type="expression", default=None)
    lib = Attribute("A library name", type="expression", default=None)
    ref = Attribute("An element reference", type="expression", required="yes")

    class Meta:
        one_of = [('app', 'lib')]

    class Help:
        synopsis = "create an element reference with an app/lib name"

    def get_value(self, context):
        app, lib, ref = self.get_parameters(context, 'app', 'lib', 'ref')
        if app is not None:
            app = self.archive.get_app(app)
        if lib is not None:
            lib = self.archive.get_lib(lib)
        ref = text_type(ref)
        try:
            element = self.archive.get_element(ref, app=app, lib=lib or None)
        except Exception as e:
            self.throw('qualify-elementref.not-found',
                       'unable to look up element ({})'.format(e))
        element_ref = "{}#{}".format(element.app.name, element.element.libname)
        return element_ref
