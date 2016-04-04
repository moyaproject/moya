from __future__ import unicode_literals
"""
Elements used in exposing external services to Moya code

"""

from ..tags.context import ContextElementBase
from ..elements.elementbase import ReturnContainer
from ..compat import text_type, raw_input

import subprocess
import weakref


class ServiceCallElement(ContextElementBase):
    """A psuedo element that proxies a Python callable"""
    xmlns = "http://moyaproject.com/db"
    _element_class = "logic"
    #_call = True

    class Meta:
        is_call = True
        app_first_arg = True

    def __init__(self, archive, element_name, service_callable, document):
        self.libname = element_name
        self.service = service_callable
        self._document = weakref.ref(document)
        self.parent_docid = None
        self._tag_name = "ServiceCall"
        self._children = ()
        self._attributes = {}
        self._code = ''  # TODO
        self._libid = None
        self.source_line = 0
        self._element_type = ('http://moyaproject.com', '')

        self._location = text_type(service_callable.__code__)

    def __iter__(self):
        yield self

    def check(self, context):
        return True

    def close(self):
        pass

    def logic(self, context):
        try:
            call = context[".call"]
            args = call.pop('args', ())

            if context.get('._winpdb_debug', False):
                password = context.get('._winpdb_password', 'password')
                del context['._winpdb_debug']
                del context['._winpdb_password']
                try:
                    import rpdb2
                except ImportError:
                    context['.console'].text("rpdb2 is required to debug with WinPDB", fg="red", bold=True)
                else:
                    context['.console'].text("Reading to launch winpdb... Click File -> Attach and enter password '{}'".format(password), fg="green", bold=True)
                    raw_input("Hit <RETURN> to continue ")
                    subprocess.Popen(["winpdb"])
                    rpdb2.start_embedded_debugger(password)

            if getattr(self.service, 'call_with_context', False):
                ret = self.service(context, *args, **call)
            else:
                ret = self.service(*args, **call)
            context["_return"] = ReturnContainer(ret)
        except Exception as e:
            raise
            #from traceback import print_exc
            #print_exc(e)
