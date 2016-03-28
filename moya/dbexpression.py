from __future__ import unicode_literals
from __future__ import print_function

from .context import dataindex
from .context.tools import to_expression
from .compat import implements_to_string, text_type
from .context.missing import is_missing
from .interface import unproxy

from pyparsing import (Word,
                       WordEnd,
                       nums,
                       alphas,
                       Combine,
                       oneOf,
                       opAssoc,
                       operatorPrecedence,
                       QuotedString,
                       Literal,
                       ParserElement,
                       ParseException,
                       Forward,
                       Group,
                       Suppress,
                       Optional,
                       Regex)
ParserElement.enablePackrat()

from sqlalchemy import and_, or_, func

import operator
import re
import threading


def dbobject(obj):
    return getattr(obj, '__moyadbobject__', lambda: obj)()


@implements_to_string
class DBExpressionError(Exception):
    hide_py_traceback = True
    error_type = "Database expression error"

    def __init__(self, exp, msg=None, col=None):
        self.exp = exp
        self.msg = msg or ''
        self.col = col

    def __str__(self):
        return self.msg

    def __moyaconsole__(self, console):
        indent = ''
        console(indent + self.exp, bold=True, fg="magenta").nl()
        if self.col:
            console(indent)(' ' * (self.col - 1) + '^', bold=True, fg="red").nl()


class DBEvalError(Exception):
    pass


def pairs(tokenlist):
    """Converts a list in to a sequence of paired values"""
    return zip(tokenlist[::2], tokenlist[1::2])


class ExpressionContext(object):
    def __init__(self, exp):
        self.exp = exp
        self._joins = []
        super(ExpressionContext, self).__init__()

    def __repr__(self):
        return "<expressioncontext '{}'>".format(self.exp)

    def add_joins(self, joins):
        self._joins.append(joins)

    def process_qs(self, qs):
        # TODO: Is this deprecated now?
        for j in self._joins:
            if isinstance(j, (tuple, list)):
                qs = qs.join(*j)
            else:
                qs = qs.join(j)
        return qs


class ExpressionModifiers(object):

    def abs(self, context, v):
        return func.abs(v)

    def count(self, context, v):
        return func.count(v)

    def sum(self, context, v):
        return func.sum(v)

    def min(self, context, v):
        return func.min(v)

    def max(self, context, v):
        return func.max(v)

    def lower(self, context, v):
        return func.lower(v)


class EvalModifierOp(object):
    modifiers = ExpressionModifiers()

    def __init__(self, tokens):

        filter, value = tokens[0]
        self.value = value
        self._eval = value.eval
        try:
            self.filter_func = getattr(self.modifiers, filter[:-1])
        except AttributeError:
            raise ValueError("unknown filter type '%s'" % filter)

    def eval(self, archive, context, app, exp_context):
        return self.filter_func(context, self._eval(archive, context, app, exp_context))


class EvalMultOp(object):
    "Class to evaluate multiplication and division expressions"

    ops = {"*": operator.imul,
           "/": operator.itruediv,
           "//": operator.ifloordiv,
           "%": operator.imod
           }

    def __init__(self, tokens):
        self.value = tokens[0]
        self._eval = self.value[0].eval
        ops = self.ops
        self.operator_eval = [(ops[op], val.eval) for op, val in pairs(self.value[1:])]

    def eval(self, archive, context, app, exp_context):
        prod = self._eval(archive, context, app, exp)
        for op_func, _eval in self.operator_eval:
            prod = op_func(prod, _eval(archive, context, app, exp_context))
        return prod


class EvalAddOp(object):
    "Class to evaluate addition and subtraction expressions"

    ops = {'+': operator.add,
           '-': operator.sub}

    def __init__(self, tokens):
        self.value = tokens[0]
        self._eval = self.value[0].eval
        ops = self.ops
        self.operator_eval = [(ops[op], val.eval) for op, val in pairs(self.value[1:])]

    def eval(self, archive, context, app, exp_context):
        sum = self._eval(archive, context, app, exp_context)
        for op_func, _eval in self.operator_eval:
            sum = op_func(sum, _eval(archive, context, app, exp_context))
        return sum


class EvalConstant(object):
    """Evaluates a constant"""
    constants = {"None": None,
                 "True": True,
                 "False": False,
                 "yes": True,
                 "no": False}

    def __init__(self, tokens):
        self.key = tokens[0]
        self.value = self.constants[self.key]

    def eval(self, archive, context, app, exp_context):
        return self.value


class EvalInteger(object):
    "Class to evaluate an integer value"
    def __init__(self, tokens):
        self.value = int(tokens[0])

    def eval(self, archive, context, app, exp_context):
        return self.value


class EvalReal(object):
    "Class to evaluate a real number value"
    def __init__(self, tokens):
        self.value = float(tokens[0])

    def eval(self, archive, context, app, exp_context):
        return self.value


class EvalString(object):
    "Class to evaluate a string"
    def __init__(self, tokens):
        self.value = tokens[0]

    def eval(self, archive, context, app, exp_context):
        return self.value


def qs(value):
    if hasattr(value, '__moyadbobject__'):
        value = value.__moyadbobject__()
    if hasattr(value, '_get_query_set'):
        value = value._get_query_set()
    if isinstance(value, list):
        return [getattr(v, 'id', v) for v in value]
    return value


class EvalVariable(object):
    "Class to evaluate a parsed variable"
    def __init__(self, tokens):
        key = tokens[0]
        self.index = dataindex.parse(key)

    def eval(self, archive, context, app, exp_context):
        value = context[self.index]
        if is_missing(value):
            raise DBEvalError("Database expression value '{}' is missing from the context".format(self.index))
        return dbobject(unproxy(value))


class EvalModelReference(object):
    """Gets a model reference"""

    _ref_model_ref = re.compile('^(.*?#.*?)(?:\.(.*?))?$')

    def __init__(self, tokens):
        self.index = tokens[0]

    def eval(self, archive, context, app, exp_context):
        model_ref, index = self._ref_model_ref.match(self.index).groups()

        app = app or context.get('.app', None)
        if app is None:
            raise DBEvalError("unable to get app from '{}'".format(self.index))

        if index is None:
            app, model_element = app.get_element(model_ref)
            try:
                table_class = model_element.get_table_class(app)
            except Exception as e:
                raise DBEvalError(str(e))
            return table_class

        index = list(dataindex.parse(index))

        app, model_element = app.get_element(model_ref)
        try:
            table_class = model_element.get_table_class(app)
        except Exception as e:
            raise DBEvalError(str(e))

        try:
            model_reference_result = table_class._get_index(archive, context, app, exp_context, index)
        except (KeyError, AttributeError):
            raise DBEvalError('no column or object called "{}"'.format(self.index))
        else:
            return model_reference_result


class EvalComparisonOp(object):
    "Class to evaluate comparison expressions"

    @classmethod
    def match_re(cls, a, b):
        return bool(b.match(a))

    @classmethod
    def escape_like(cls, like, _should_escape="\\%_".__contains__):
        """escape LIKE comparisons"""
        if not isinstance(like, text_type):
            return like
        return ''.join("\\" + c if _should_escape(c) else c for c in like)

    def in_(context, a, b):
        if hasattr(b, '__moyadbsubselect__'):
            sub_b = b.__moyadbsubselect__(context)
            if sub_b is not None:
                b = sub_b
        a = qs(a)
        try:
            return a.in_(qs(b))
        except:
            raise DBEvalError("db expression 'in' operator works on columns only (did you mean .id)?")

    def notin_(context, a, b):
        if hasattr(b, '__moyadbsubselect__'):
            sub_b = b.__moyadbsubselect__(context)
            if sub_b is not None:
                b = sub_b
        a = qs(a)
        try:
            return a.notin_(qs(b))
        except:
            raise DBEvalError("db expression 'not in' operator works on columns only (did you mean .id)?")

    def contains_(context, a, b):
        try:
            return qs(a).contains(qs(b))
        except:
            raise DBEvalError("value {} is an invalid operand for the 'contains' operator".format(to_expression(context, b)))

    def icontains_(context, a, b):
        if not isinstance(b, text_type):
            raise DBEvalError("icontains right hand side should be a string, not {}".format(context.to_expr(b)))

        b = "%{}%".format(EvalComparisonOp.escape_like(b))
        return qs(a).like(b)

    def ieq(context, a, b):
        if not isinstance(b, text_type):
            raise DBEvalError("case insensitive equality operator (~=) right hand side should be a string, not {}".format(context.to_expr(b)))

        return qs(a).ilike(EvalComparisonOp.escape_like(b), escape='\\')

    opMap = {
        "<": lambda c, a, b: qs(a) < qs(b),
        "lt": lambda c, a, b: qs(a) < qs(b),
        "<=": lambda c, a, b: qs(a) <= qs(b),
        "lte": lambda c, a, b: qs(a) <= qs(b),
        ">": lambda c, a, b: qs(a) > qs(b),
        "gt": lambda c, a, b: qs(a) > qs(b),
        ">=": lambda c, a, b: qs(a) >= qs(b),
        "gte": lambda c, a, b: qs(a) >= qs(b),
        "!=": lambda c, a, b: qs(a) != qs(b),
        "==": lambda c, a, b: qs(a) == qs(b),
        'like': lambda c, a, b: qs(a).like(qs(b)),
        'ilike': lambda c, a, b: qs(a).ilike(qs(b)),

        #"~=": lambda c, a, b: qs(a).ilike(qs(EvalComparisonOp.escape_like(b)), escape='\\'),
        "~=": ieq,
        "^=": lambda c, a, b: qs(a).startswith(qs(b)),
        "$=": lambda c, a, b: qs(a).endswith(qs(b)),
        "in": in_,
        "not in": notin_,
        "contains": contains_,
        "icontains": icontains_,
        #"icontains": lambda c, a, b: qs(a).like('%' + EvalComparisonOp.escape_like(b) + '%', escape='\\')
    }

    def __init__(self, tokens):
        self.value = tokens[0]
        self._eval = self.value[0].eval
        self.operator_eval = [(self.opMap[op], val.eval) for op, val in pairs(self.value[1:])]

    def eval(self, archive, context, app, exp_context):
        val1 = self._eval(archive, context, app, exp_context)
        for op_func, _eval in self.operator_eval:
            val2 = _eval(archive, context, app, exp_context)
            val1 = op_func(context, val1, val2)
        return val1


class EvalLogicOpAND(object):

    def __init__(self, tokens):
        self.value = tokens[0]
        self._eval = self.value[0].eval
        self.operator_eval = [val.eval for op, val in pairs(self.value[1:])]

    def eval(self, archive, context, app, exp_context):
        val1 = self._eval(archive, context, app, exp_context)
        for _eval in self.operator_eval:
            val2 = _eval(archive, context, app, exp_context)
            val1 = and_(val1, val2)
        return val1


class EvalLogicOpOR(object):

    def __init__(self, tokens):
        self.value = tokens[0]
        self._eval = self.value[0].eval
        self.operator_eval = [val.eval for op, val in pairs(self.value[1:])]

    def eval(self, archive, context, app, exp_context):
        val1 = self._eval(archive, context, app, exp_context)
        for _eval in self.operator_eval:
            val2 = _eval(archive, context, app, exp_context)
            val1 = or_(val1, val2)
        return val1


class EvalGroupOp(object):
    def __init__(self, tokens):
        self._evals = [t.eval for t in tokens[0][0::2]]

    def eval(self, archive, context, app, exp_context):
        val = [eval(archive, context, app, exp_context) for eval in self._evals]
        return val


integer = Word(nums)
real = Combine(Word(nums) + '.' + Word(nums))

constant = (Literal('True') |
            Literal('False') |
            Literal('None') |
            Literal('yes') |
            Literal('no')) + WordEnd()

model_reference = Regex(r'([\w\.]*#[\w\.]+)')
variable = Regex(r'([a-zA-Z0-9\._]+)')

string = QuotedString('"', escChar="\\") | QuotedString('\'', escChar="\\")
operand = model_reference | real | integer | constant | string | variable

plusop = oneOf('+ -')
multop = oneOf('* / // %')
groupop = Literal(',')

expr = Forward()

modifier = Combine(Word(alphas + nums) + ':')

integer.setParseAction(EvalInteger)
real.setParseAction(EvalReal)
string.setParseAction(EvalString)
constant.setParseAction(EvalConstant)
variable.setParseAction(EvalVariable)
model_reference.setParseAction(EvalModelReference)

comparisonop = (oneOf("< <= > >= != == ~= ^= $=") |
                (Literal('not in') + WordEnd()) |
                (oneOf("in lt lte gt gte matches contains icontains like ilike") + WordEnd()))


logicopOR = Literal('or') + WordEnd()
logicopAND = Literal('and') + WordEnd()

expr << operatorPrecedence(operand, [
    (modifier, 1, opAssoc.RIGHT, EvalModifierOp),
    (multop, 2, opAssoc.LEFT, EvalMultOp),
    (plusop, 2, opAssoc.LEFT, EvalAddOp),
    (comparisonop, 2, opAssoc.LEFT, EvalComparisonOp),

    (logicopAND, 2, opAssoc.LEFT, EvalLogicOpAND),
    (logicopOR, 2, opAssoc.LEFT, EvalLogicOpOR),

    (groupop, 2, opAssoc.LEFT, EvalGroupOp),
])


@implements_to_string
class DBExpression(object):
    exp_cache = {}
    _lock = threading.Lock()

    def __init__(self, exp):
        self.exp = exp

    def __repr__(self):
        return "<DBExpression \"%s\">" % self.exp

    def __str__(self):
        return self.exp

    def eval(self, archive, context, app=None):
        exp_context = ExpressionContext(self.exp)
        eval = self.compile_cache(self.exp)
        try:
            result = eval(archive, context, app, exp_context)
        except DBEvalError as e:
            raise DBExpressionError(self.exp, text_type(e))
        return result

    def eval2(self, archive, context, app=None):
        exp_context = ExpressionContext(self.exp)
        eval = self.compile_cache(self.exp)
        try:
            result = eval(archive, context, app, exp_context)
        except DBEvalError as e:
            raise DBExpressionError(self.exp, text_type(e))
        return result, exp_context

    def compile(self):
        return self.compile_cache(self.exp)

    def compile_cache(self, exp):
        with self._lock:
            try:
                return self.exp_cache[exp]
            except KeyError:
                try:
                    compiled_exp = expr.parseString(exp, parseAll=True)
                except ParseException as e:
                    raise DBExpressionError(exp, text_type(e), col=e.col)
                eval = self.exp_cache[exp] = compiled_exp[0].eval
                return eval


if __name__ == "__main__":

    """
    <db:filter model="#TagDB">#TagDB.name==name and #TagDB.company.pk==company_pk</db:filter>

    """

    exp = DBExpression("moya.auth#User.username=='will'")

    print(exp.compile())

    exp = DBExpression("auth#User.username=='will'")

    print(exp.compile())

    exp = DBExpression("comments#Comment.namespace == app.name and comments#Comment.object in comment_keys")

    print(exp.compile())

    exp = DBExpression("#CommentObject.count + 1")

    print(exp.compile)
