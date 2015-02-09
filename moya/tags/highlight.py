from __future__ import unicode_literals

from ..elements.elementbase import Attribute, LogicElement
from .. import syntax


class Highlight(LogicElement):
    """This tag is used by the Moya debug library to syntax highlight code (turning it into HTML in the process)."""

    class Help:
        synopsis = "syntax highlight code"

    dst = Attribute("Destination to store exception object", type="reference", required=True)
    code = Attribute("Code to highlight", type="reference", required=True)
    format = Attribute("Format of code", required=True, default="xml")
    highlight = Attribute("Line numbers to highlight", type="expression", required=False, default=None)

    def logic(self, context):
        params = self.get_parameters(context)
        highlight = params.highlight or []
        if not isinstance(highlight, list):
            highlight = [highlight]
        code = context[params.code]
        html = syntax.highlight(params.format, code, highlight_lines=highlight)
        context[params.dst] = html
