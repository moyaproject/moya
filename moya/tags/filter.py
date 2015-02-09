from __future__ import unicode_literals
from ..elements.elementbase import LogicElement, Attribute
from ..filter import MoyaFilter, MoyaFilterExpression


class Filter(LogicElement):
    """
    Define a [i]filter[/i], which may be used in expressions.

    Here's an example of a filter:

    [code xml]
    <filter name="repeat">
        <return-str>${str:value * count}</return-str>
    </filter>
    [/code]

    And here is how you might use it in an expression:

    [code xml]
    <echo>${"beetlejuice "|repeat(count=3)}</echo>
    [/code]
    """

    class Help:
        synopsis = "define a filter"

    name = Attribute("Filter name", required=True)
    value = Attribute("Value name", default="value", required=False)
    expression = Attribute("Expression", type="function", required=False, default=None)

    def lib_finalize(self, context):
        expression = self.expression(context)
        value_name = self.value(context)
        if expression is not None:
            _filter = MoyaFilterExpression(expression, value_name)
        else:
            _filter = MoyaFilter(self.lib, self.libid, value_name)
        self.lib.register_filter(self.name(context), _filter)
