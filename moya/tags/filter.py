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
    missing = Attribute("Allow missing values?", type="boolean", default=False, required=False)

    def lib_finalize(self, context):
        validator = None

        for signature in self.children('signature'):
            validator = signature.get_validator(context)

        expression = self.expression(context)
        value_name = self.value(context)
        allow_missing = self.missing(context)
        if expression is not None:
            _filter = MoyaFilterExpression(expression, value_name, allow_missing=allow_missing)
        else:
            _filter = MoyaFilter(self.lib, self.libid, value_name, allow_missing=allow_missing, validator=validator)
        self.lib.register_filter(self.name(context), _filter)
