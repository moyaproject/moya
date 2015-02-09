from __future__ import unicode_literals

from ..elements.elementbase import Attribute
from ..tags.context import ContextElementBase
from .. import namespaces
from .. import logic


class Check(ContextElementBase):
    """A pre-flight check"""
    xmlns = namespaces.preflight

    class Help:
        synopsis = "define a pre-flight test"


class Result(ContextElementBase):
    xmlns = namespaces.preflight
    exit = Attribute("Also exit the check", type="boolean", default=False)
    status = None

    class Help:
        undocumented = True

    def logic(self, context):
        check = self.get_ancestor((self.xmlns, "check"))
        text = context.sub(self.text)
        context['.preflight'].append((check, self.status, text))
        if self.exit(context):
            raise logic.Unwind()


class Pass(Result):
    status = "pass"

    class Help:
        synopsis = "pass a preflight check"


class Fail(Result):
    status = "fail"

    class Help:
        synopsis = "fail a preflight check"


class Warning(Result):
    status = "warning"

    class Help:
        synopsis = "add a warning result to a preflight check"
