"""
Parse and evaluate Moya expressions

This module contains some quite shocking micro-optimizations to offset the extra work when compared to Python expressions.

The optimizations were guided by the mandel.xml benchmark which has improved by many orders of magnitude since the first version.

"""
from __future__ import unicode_literals
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from fs.path import basename
from fs import wildcard

from pyparsing import (Word,
                       WordEnd,
                       Empty,
                       nums,
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
                       Regex,
                       delimitedList,
                       Optional)

from .. import __version__
from ..context import dataindex
from ..context.dataindex import parse as parseindex
from ..context.expressiontime import TimeSpan
from ..context.expressionrange import ExpressionRange
from ..context.tools import to_expression, decode_string
from ..context.missing import Missing
from ..moyaexceptions import throw
from ..compat import implements_to_string, text_type, string_types
from ..context.modifiers import ExpressionModifiers
from ..moyaexceptions import MoyaException
from ..errors import LogicError
from operator import methodcaller

import operator
import re
import sys
from operator import truth
import threading

ParserElement.enablePackrat()
sys.setrecursionlimit(10000)

VERSION = 2


@implements_to_string
class ExpressionError(Exception):
    def __init__(self, exp, msg=None, col=None, original=None):
        super(ExpressionError, self).__init__()
        self.exp = exp
        self.msg = msg or ''
        self.original = original
        self.col = col

    def __str__(self):
        return self.msg

    def __repr__(self):
        if self.original:
            return "%s '%s': %s" % (self.msg, self.exp, text_type(self.original))
        else:
            return "%s '%s'" % (self.msg, self.exp)

    def __moyaconsole__(self, console):
        indent = ''
        console(indent + self.exp, bold=True, fg="magenta").nl()
        if self.col:
            console(indent)(' ' * (self.col - 1) + '^', bold=True, fg="red").nl()


class ExpressionCompileError(ExpressionError):
    pass


@implements_to_string
class ExpressionEvalError(ExpressionError):

    def __str__(self):
        if self.original:
            return "%s '%s': %s" % (self.msg, self.exp, text_type(self.original))
        else:
            return "%s '%s'" % (self.msg, self.exp)


class Evaluator(object):
    """Base class mainly to make expressions pickleable"""
    def __init__(self, s, loc, tokens):
        self.col = loc
        self.tokens = tokens.asList()
        self.build(tokens)

        super(Evaluator, self).__init__()

    def build(self, tokens):
        pass

    def eval(self, context):
        raise NotImplementedError

    def __getstate__(self):
        return self.tokens

    def __setstate__(self, state):
        self.tokens = state
        self.build(state)


class EvalConstant(Evaluator):
    """Evaluates a constant"""
    constants = {"None": None,
                 "True": True,
                 "False": False,
                 "yes": True,
                 "no": False}

    def build(self, tokens):
        self.key = tokens[0]
        value = self.value = self.constants[self.key]
        self.eval = lambda context: value


class EvalVariable(Evaluator):
    """Class to evaluate a parsed variable"""
    def build(self, tokens):
        self.key = tokens[0]
        self._index = index = dataindex.parse(self.key)
        if index.from_root or len(index) > 1:
            self.eval = methodcaller('__getitem__', self._index)
        else:
            self.eval = methodcaller('get_simple', self.key)


class EvalLiteralIndex(Evaluator):
    def build(self, tokens):
        self.scope = tokens[0][0].eval
        self.indices = [dataindex.parse(t[1:]) for t in tokens[0][1:]]

    def eval(self, context):
        obj = self.scope(context)
        for index in self.indices:
            with context.data_frame(obj):
                obj = context[index]
        return obj


@implements_to_string
class EvalRegExp(Evaluator):
    """Class to evaluate a parsed variable"""
    def build(self, tokens):
        self.regexp = tokens[0]
        self._re = re.compile(tokens[0])
        self.match = self._re.match

    def __str__(self):
        return "/%s/" % self.regexp

    def __repr__(self):
        return "/%s/" % self.regexp

    def eval(self, context):
        return self


@implements_to_string
class EvalTimespan(Evaluator):
    """Evaluate a timespan spec"""
    def build(self, tokens):
        self.ts = TimeSpan(tokens[0])

    def __str__(self):
        return text_type(self.ts)

    def eval(self, context):
        return self.ts


class EvalCurrentScope(Evaluator):
    """Class to eval the current scope"""

    def eval(self, context):
        return context.obj
        #return context.capture_scope()


class EvalExplicitVariable(Evaluator):
    """Class to evaluate a parsed constant or explicit variable (beginning with $)"""
    def build(self, tokens):
        self.index = parseindex(tokens[1])

    def eval(self, context):
        return context[self.index]


class EvalInteger(Evaluator):
    """Class to evaluate an integer value"""
    def build(self, tokens):
        value = self.value = int(tokens[0])
        self.eval = lambda context: value


class EvalReal(Evaluator):
    """Class to evaluate a real number value"""
    def build(self, tokens):
        value = self.value = float(tokens[0])
        self.eval = lambda context: value


class EvalTripleString(Evaluator):
    """Class to evaluate a triple quoted string"""

    def build(self, tokens, _decode=decode_string):
        value = self.value = _decode(tokens[0][3:-3])
        self.eval = lambda context: value


class EvalString(Evaluator):
    """Class to evaluate a string"""

    def build(self, tokens, _decode=decode_string):
        value = self.value = _decode(tokens[0][1:-1])
        self.eval = lambda context: value


class EvalSignOp(Evaluator):
    """Class to evaluate expressions with a leading + or - sign"""
    def build(self, tokens):
        sign, value = tokens[0]
        if sign == "+":
            self.eval_func = operator.pos
        elif sign == "-":
            self.eval_func = operator.neg
        self._eval = value.eval

    def eval(self, context):
        return self.eval_func(self._eval(context))


class EvalNotOp(Evaluator):
    """Class to evaluate expressions with logical NOT"""
    def build(self, tokens):
        sign, value = tokens[0]
        _eval = self._eval = value.eval
        self.eval = lambda context: not _eval(context)


class EvalList(Evaluator):
    """Class to evaluate a parsed variable"""
    def build(self, tokens):
        self.list_tokens = [t.eval for t in tokens]

    def eval(self, context):
        return [_eval(context) for _eval in self.list_tokens]


class EvalSimpleList(Evaluator):
    """Class to evaluate a parsed variable"""
    def build(self, tokens):
        self.list_tokens = [t.eval for t in tokens]

    def eval(self, context):
        return [_eval(context) for _eval in self.list_tokens]


class EvalEmptyList(Evaluator):

    def build(self, tokens):
        pass

    def eval(self, context):
        return []


class EvalDict(Evaluator):

    def build(self, tokens):
        self._item_eval = [(k.eval, v.eval) for k, v in tokens[0]]

    def eval(self, context):
        return {k(context): v(context) for k, v in self._item_eval}


class ExpFunction(object):
    def __init__(self, context, text, eval):
        self.context = context
        self.text = text
        self._eval = eval
        self._context = None

    def __repr__(self):
        return "<expression>"

    def __moyacall__(self, params):
        with self.context.data_scope(params):
            return self._eval(self.context)


class EvalFunction(Evaluator):

    def build(self, tokens):
        self._eval = tokens[0][0].eval

    def eval(self, context):
        return ExpFunction(context, '', self._eval)


class EvalKeyPairDict(Evaluator):

    def build(self, tokens):
        self._item_eval = [(k, v.eval) for k, v in tokens]

    def eval(self, context):
        return {k: v(context) for k, v in self._item_eval}


class EvalEmptyDict(Evaluator):
    def build(self, tokens):
        pass

    def eval(self, context):
        return {}


class EvalModifierOp(Evaluator):
    """Class to evaluate expressions with a leading filter function"""

    modifiers = ExpressionModifiers()

    def build(self, tokens):

        _filter, value = tokens[0]
        self.value = value
        _eval = self._eval = value.eval
        try:
            filter_func = self.filter_func = getattr(self.modifiers, _filter[:-1])
        except AttributeError:
            raise ValueError("unknown modifier '%s'" % _filter)

        self.eval = lambda context: filter_func(context, _eval(context))

    # def eval(self, context):
    #     return self.filter_func(context, self._eval(context))


class EvalFilterOp(Evaluator):
    def build(self, tokens):
        self.value = tokens[0]
        self._eval = self.value[0].eval
        self.operator_eval = [(op, val.eval) for op, val in pairs(self.value[1:])]

    def eval(self, context):
        prod = self._eval(context)
        app = context.get('.app', None)
        for op, _eval in self.operator_eval:
            filter_obj = _eval(context)

            if isinstance(filter_obj, text_type) and '.filters' in context:
                filter_obj = context['.filters'].lookup(app, filter_obj)

            if hasattr(filter_obj, '__moyafilter__'):
                prod = filter_obj.__moyafilter__(context, app, prod, {})
            else:
                if callable(filter_obj):
                    prod = filter_obj(prod)
                else:
                    raise ValueError('{} may not be used as a filter'.format(to_expression(context, filter_obj)))
        return prod


class EvalSliceOp(Evaluator):
    def build(self, tokens):
        self.value_eval = tokens[0][0].eval
        self.slice_eval = [t.eval if t is not None else (lambda c: None) for t in tokens[0][1]]
        if len(self.slice_eval) == 2:
            self.slice_eval.append(lambda context: None)
        if len(self.slice_eval) > 3:
            raise ValueError('Slice syntax takes at most 3 values, i.e. value[start:stop:step]')

    def eval(self, context):
        obj = self.value_eval(context)
        slice_indices = [_eval(context) for _eval in self.slice_eval]
        start, stop, step = (None if _s == '' else _s for _s in slice_indices)
        try:
            if hasattr(obj, 'slice'):
                return obj.slice(start, stop, step)
            else:
                return obj[start:stop:step]
        except TypeError:
            _vars = (context.to_expr(start) if start is not None else '',
                     context.to_expr(stop) if stop is not None else '',
                     context.to_expr(step) if step is not None else '')
            raise ValueError('unable to perform slice operation [{}:{}:{}]'.format(*_vars))


class EvalBraceOp(Evaluator):
    def build(self, tokens):
        self.value_eval = tokens[0][0].eval
        self.index_eval = [(t[0], t[1].eval) for t in tokens[0][1:]]

    def eval(self, context):
        obj = self.value_eval(context)
        for brace, eval in self.index_eval:
            index = eval(context)
            if brace == '[':
                if getattr(index, 'moya_missing', False):
                    raise ValueError("unable to look up missing index {!r}".format(index))
                if hasattr(obj, '__moyacontext__'):
                    obj = obj.__moyacontext__(context)
                try:
                    if hasattr(obj, '__getitem__'):
                        obj = obj[index]
                    else:
                        obj = getattr(obj, index)
                except Exception:
                    obj = Missing(text_type(index))
            else:
                if isinstance(obj, text_type) and '.filters' in context:
                    obj = context['.filters'].lookup(context.get('.app', None), obj)

                if hasattr(obj, '__moyacall__'):
                    obj = obj.__moyacall__(index)
                else:
                    raise ValueError("{} does not accept parameters".format(to_expression(context, obj)))
        return obj


def pairs(tokenlist):
    """Converts a list in to a sequence of paired values"""
    return zip(tokenlist[::2], tokenlist[1::2])


class EvalMultOp(Evaluator):
    "Class to evaluate multiplication and division expressions"

    ops = {"*": operator.mul,
           "/": operator.truediv,
           "//": operator.floordiv,
           "%": operator.mod,
           'bitand': operator.and_,
           'bitor': operator.or_,
           'bitxor': operator.xor
           }

    def build(self, tokens):
        self.value = tokens[0]
        _eval = self._eval = self.value[0].eval
        ops = self.ops
        operator_eval = self.operator_eval = [(ops[op], val.eval) for op, val in pairs(self.value[1:])]

        if len(self.operator_eval) == 1:
            op_func, rhs_eval = self.operator_eval[0]
            self.eval = lambda context: op_func(_eval(context), rhs_eval(context))
        else:
            def eval(context):
                prod = _eval(context)
                for op_func, rhs_eval in operator_eval:
                    prod = op_func(prod, rhs_eval(context))
                return prod
            self.eval = eval

    # def eval(self, context):
    #     prod = self._eval(context)
    #     for op_func, _eval in self.operator_eval:
    #         prod = op_func(prod, _eval(context))
    #     return prod


class EvalAddOp(Evaluator):
    "Class to evaluate addition and subtraction expressions"

    ops = {'+': operator.add,
           '-': operator.sub}

    def build(self, tokens):
        self.value = tokens[0]
        _eval = self._eval = self.value[0].eval
        ops = self.ops
        operator_eval = self.operator_eval = [(ops[op], val.eval) for op, val in pairs(self.value[1:])]

        if len(self.operator_eval) == 1:
            op_func, rhs_eval = self.operator_eval[0]
            self.eval = lambda context: op_func(_eval(context), rhs_eval(context))
        else:
            def eval(context):
                prod = _eval(context)
                for op_func, rhs_eval in operator_eval:
                    prod = op_func(prod, rhs_eval(context))
                return prod
            self.eval = eval

    # def eval(self, context):
    #     sum = self._eval(context)
    #     for op_func, _eval in self.operator_eval:
    #         sum = op_func(sum, _eval(context))
    #     return sum


class EvalRangeOp(Evaluator):
    def build(self, tokens):
        self._evals = [t.eval for t in tokens[0][0::2]]

    def eval(self, context):
        a, b = self._evals
        return ExpressionRange.create(context, a(context), b(context), inclusive=True)


class EvalExclusiveRangeOp(Evaluator):
    def build(self, tokens):
        self._evals = [t.eval for t in tokens[0][0::2]]

    def eval(self, context):
        a, b = self._evals
        return ExpressionRange.create(context, a(context), b(context), inclusive=False)


class EvalTernaryOp(Evaluator):

    def build(self, tokens):
        self.evals = [t.eval for t in tokens[0][::2]]

    def eval(self, context):
        condition, truthy, falsey = self.evals
        if condition(context):
            return truthy(context)
        else:
            return falsey(context)


def _match_re(a, b):
    if isinstance(b, EvalRegExp):
        return truth(b.match(text_type(a)))
    return truth(re.match(b, text_type(a)))


def wildcard_match(name, pattern):
    if isinstance(pattern, list):
        return wildcard.match_any(pattern, name)
    else:
        return wildcard.match(pattern, name)


def _in_operator(a, b):
    try:
        return a in b
    except:
        return False


def _str_in(value, seq):
    """Return True if the string representation of a value equals a
    string representation of any value in a sequence"""
    try:
        str_value = text_type(value)
        return any(str_value == text_type(value) for value in seq)
    except:
        return False


class EvalComparisonOp(Evaluator):
    "Class to evaluate comparison expressions"

    opMap = {
        "<": operator.lt,
        "lt": operator.lt,
        "<=": operator.le,
        "lte": operator.le,
        ">": operator.gt,
        "gt": operator.gt,
        ">=": operator.ge,
        "gte": operator.ge,
        "!=": operator.ne,
        "==": operator.eq,
        "~=": lambda a, b: text_type(a).lower() == text_type(b).lower(),
        "^=": lambda a, b: text_type(a).startswith(text_type(b)),
        "$=": lambda a, b: text_type(a).endswith(text_type(b)),
        "is": operator.is_,
        "is not": operator.is_not,
        "in": _in_operator,
        "not in": lambda a, b: not _in_operator(a, b),
        "instr": _str_in,
        "not instr": lambda a, b: not _str_in(a, b),
        "matches": _match_re,
        "fnmatches": wildcard_match
    }

    def build(self, tokens):
        self.value = tokens[0]
        self._eval = self.value[0].eval
        self.operator_eval = [(self.opMap[op], val.eval) for op, val in pairs(self.value[1:])]

    def eval(self, context):
        val1 = self._eval(context)
        for op_func, _eval in self.operator_eval:
            val2 = _eval(context)
            val1 = op_func(val1, val2)
            if not val1:
                return False
        return True


class EvalFormatOp(Evaluator):

    def build(self, tokens):
        self.value = tokens[0]
        self._eval = self.value[0].eval
        self.evals = [val.eval for op, val in pairs(self.value[1:])]

    def eval(self, context):
        val1 = self._eval(context)
        for _eval in self.evals:
            fmt = _eval(context)
            if not isinstance(fmt, string_types):
                raise ValueError('format should be a string, not {!r}'.format(fmt))
            return format(val1, fmt)

        return val1


class EvalLogicOpOR(Evaluator):

    def build(self, tokens):
        self.value = tokens[0]
        self._eval = self.value[0].eval
        self.operator_eval = [val.eval for op, val in pairs(self.value[1:])]

    def eval(self, context):
        val1 = self._eval(context)
        if val1:
            return val1
        for _eval in self.operator_eval:
            val2 = _eval(context)
            val1 = val1 or val2
            if val1:
                return val1
        return val1


class EvalLogicOpAND(Evaluator):

    def build(self, tokens):
        self.value = tokens[0]
        self._eval = self.value[0].eval
        self.operator_eval = [val.eval for op, val in pairs(self.value[1:])]

    def eval(self, context):
        val1 = self._eval(context)
        if not val1:
            return val1
        for _eval in self.operator_eval:
            val2 = _eval(context)
            val1 = val1 and val2
            if not val1:
                return val1
        return val1

word_characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_0123456789'
expr = Forward()

# define the parser
integer = Word(nums)
real = Combine(Word(nums) + "." + Word(nums))

constant = oneOf('True False None yes no') + WordEnd(word_characters)

# TODO: expand on variable regex
simple_variable = Regex(r'([a-zA-Z0-9_]+)')
variable = Regex(r'([a-zA-Z0-9\._]+)')
explicit_variable = '$' + Regex(r'([a-zA-Z0-9\._]+)')
current_scope = Literal('$$')

triple_string = (QuotedString("'''", escChar=None, unquoteResults=False) |
                 QuotedString('"""', escChar=None, unquoteResults=False))

string = (QuotedString('"', escChar='\\', unquoteResults=False) |
          QuotedString("'", escChar="\\", unquoteResults=False))

regexp = QuotedString('/', escChar=None)
timespan = Combine(Word(nums) + oneOf('ms s m h d'))

current_scope_operand = current_scope
variable_operand = variable
#simple_variable_operand = simple_variable
explicit_variable_operand = explicit_variable
integer_operand = integer
real_operand = real
number_operand = real | integer
triple_string_operand = triple_string
string_operand = string

groupop = Literal(',')
signop = oneOf('+ -')
multop = oneOf('* / // % bitand bitor')
filterop = oneOf('|')
plusop = oneOf('+ -')
notop = Literal('not') + WordEnd(word_characters)

rangeop = Literal('..')
exclusiverangeop = Literal('...')
ternaryop = ('?', ':')

current_scope_operand.setParseAction(EvalCurrentScope)
variable_operand.setParseAction(EvalVariable)
explicit_variable_operand.setParseAction(EvalExplicitVariable)
integer_operand.setParseAction(EvalInteger)
real_operand.setParseAction(EvalReal)
triple_string.setParseAction(EvalTripleString)
string_operand.setParseAction(EvalString)
constant.setParseAction(EvalConstant)
regexp.setParseAction(EvalRegExp)
timespan.setParseAction(EvalTimespan)

modifier = Regex(r'([a-zA-Z][a-zA-Z0-9_]*)\:')

simple_list_operand = Group(delimitedList(expr))
simple_list_operand.setParseAction(EvalSimpleList)

list_operand = (Suppress('[') + delimitedList(expr) + Suppress(']'))
list_operand.setParseAction(EvalList)

empty_list_operand = Literal('[]')
empty_list_operand.setParseAction(EvalEmptyList)

dict_item = Group(expr + Suppress(Literal(':')) + expr)
dict_operand = Group(Suppress('{') + delimitedList(dict_item) + Suppress('}'))
dict_operand.setParseAction(EvalDict)

empty_dict_operand = Literal('{}')
empty_dict_operand.setParseAction(EvalEmptyDict)

function_operand = Group(Suppress('`') + expr + Suppress('`'))
function_operand.setParseAction(EvalFunction)

key_pair = Group(Regex(r'([a-zA-Z0-9_]+)') + Suppress(Literal('=') + WordEnd('=!+-*/')) + expr)
key_pair_dict_operand = delimitedList(key_pair)
key_pair_dict_operand.setParseAction(EvalKeyPairDict)

callop = Group(('(') + expr + Suppress(')'))
index = Group(('[') + expr + Suppress(']'))

_slice = Group(Suppress('[') + delimitedList(Optional(expr, default=None), ':') + Suppress(']'))

braceop = callop | index
sliceop = _slice

literalindex = Regex(r'\.([a-zA-Z0-9\._]+)')

operand = (
   timespan |
   real_operand |
   integer_operand |
   triple_string_operand |
   string_operand |
   regexp |
   constant |
   function_operand |
   key_pair_dict_operand |
   current_scope_operand |
   explicit_variable_operand |
   variable_operand |
   empty_list_operand |
   empty_dict_operand |
   list_operand |
   dict_operand
)

comparisonop = (oneOf("< <= > >= != == ~= ^= $=") |
                (Literal('not in') + WordEnd()) |
                (Literal('not instr') + WordEnd()) |
                (Literal('is not') + WordEnd()) |
                (oneOf("is in instr lt lte gt gte matches fnmatches") + WordEnd()))

logicopOR = Literal('or') + WordEnd()
logicopAND = Literal('and') + WordEnd()
formatop = Literal('::')

expr << operatorPrecedence(operand, [

    (signop, 1, opAssoc.RIGHT, EvalSignOp),
    (exclusiverangeop, 2, opAssoc.LEFT, EvalExclusiveRangeOp),
    (rangeop, 2, opAssoc.LEFT, EvalRangeOp),

    (braceop, 1, opAssoc.LEFT, EvalBraceOp),
    (sliceop, 1, opAssoc.LEFT, EvalSliceOp),
    (literalindex, 1, opAssoc.LEFT, EvalLiteralIndex),

    (modifier, 1, opAssoc.RIGHT, EvalModifierOp),

    (formatop, 2, opAssoc.LEFT, EvalFormatOp),

    (multop, 2, opAssoc.LEFT, EvalMultOp),
    (plusop, 2, opAssoc.LEFT, EvalAddOp),

    (filterop, 2, opAssoc.LEFT, EvalFilterOp),

    (comparisonop, 2, opAssoc.LEFT, EvalComparisonOp),
    (notop, 1, opAssoc.RIGHT, EvalNotOp),

    (logicopAND, 2, opAssoc.LEFT, EvalLogicOpAND),
    (logicopOR, 2, opAssoc.LEFT, EvalLogicOpOR),

    (ternaryop, 3, opAssoc.LEFT, EvalTernaryOp),
])

#expr.validate()


class DummyLock(object):
    """Replacement for real lock that does nothing"""
    def __enter__(self):
        pass

    def __exit__(self, *args, **kwargs):
        pass


class Function(object):
    def __init__(self, expression, scope=None):
        self.expression = expression
        if scope is None:
            scope = {}
        self.scope = scope

    def __repr__(self):
        return '<function "{}">'.format(self.expression.exp)

    def __call__(self, context, **params):
        with context.data_frame(params):
            with context.data_scope(self.scope):
                return self.expression.eval(context)

    def call(self, context, params):
        with context.data_frame(params):
            with context.data_scope(self.scope):
                return self.expression.eval(context)

    def get_callable(self, context):
        def call(params):
            with context.data_frame(params):
                with context.data_scope(self.scope):
                    return self.expression.eval(context)
        return call

    def get_scope_callable(self, context):
        def callscope(scope):
            with context.data_scope(scope):
                return self.expression.eval(context)
        return callscope


@implements_to_string
class Expression(object):
    """Evaluate an arithmetic expression of context values"""

    exp_cache = {}
    new_expressions = set()
    _lock = threading.RLock()

    def __init__(self, exp):
        self.exp = exp
        self.compiled_exp = None
        self._eval = self._lazy_compile_eval
        self.new_expressions.add(exp)

    def _lazy_compile_eval(self, context):
        self.compile()
        return self._eval(context)

    def compile(self):
        self.compiled_exp = self.compile_cache(self.exp)
        self._eval = self.compiled_exp[0].eval
        return self

    def eval(self, context, _hasattr=hasattr):
        try:
            obj = self._eval(context)
            return obj.__moyacontext__(context) if _hasattr(obj, '__moyacontext__') else obj
        except (ExpressionError, MoyaException, LogicError):
            raise
        except ArithmeticError as e:
            if isinstance(e, ZeroDivisionError):
                throw('math.division-error',
                      "Can't divide by zero in '{}'".format(self.exp),
                      diagnosis="Check your math")
            else:
                throw('math.arithmetic-error', text_type(e))
        except Exception as e:
            if context['.develop']:
                print("In expression.eval {!r}".format(self))
                import traceback
                traceback.print_exc(e)

            raise ExpressionEvalError(self.exp, original=e)

    def make_function(self, context=None):
        """Returns a callable from this expression"""
        return Function(self, context.obj if context else None)

    def __repr__(self):
        return "Expression(%r)" % self.exp

    def __str__(self):
        return self.exp

    def __getstate__(self):
        self.compiled_exp = self.compile_cache(self.exp)
        return (self.exp, self.compiled_exp)

    def __setstate__(self, state):
        """Bit of magic to lazily compile expressions after unpickling"""
        self.exp, self.compiled_exp = state
        self.exp_cache[self.exp] = self.compiled_exp
        self._eval = self.compiled_exp[0].eval

    @classmethod
    def insert_expressions(cls, expressions):
        exp_cache = cls.exp_cache
        for expression in expressions:
            if expression.exp not in exp_cache:
                exp_cache[expression.exp] = expression.compiled_exp

    @classmethod
    def dump(cls, cache):
        name = "expcache.{}.{}".format(VERSION, __version__)
        cache.set(name, cls.exp_cache)

    @classmethod
    def load(cls, cache):
        name = "expcache.{}.{}".format(VERSION, __version__)
        exp = cache.get(name, None)
        if exp is not None:
            cls.exp_cache.update(exp)
            return True
        return False

    @classmethod
    def get_eval(cls, exp, context):
        with cls._lock:
            try:
                compiled_exp = cls.exp_cache[exp]
            except KeyError:
                try:
                    compiled_exp = cls.exp_cache[exp] = expr.parseString(exp, parseAll=True).asList()
                except ParseException as e:
                    raise ExpressionCompileError(exp, 'unable to parse expression "{}"'.format(exp), col=e.col, original=e)
            return compiled_exp[0].eval(context)

    @classmethod
    def compile_cache(cls, exp):
        with cls._lock:
            try:
                return cls.exp_cache[exp]
            except KeyError:
                try:
                    compiled_exp = cls.exp_cache[exp] = expr.parseString(exp, parseAll=True).asList()
                    return compiled_exp
                except ParseException as e:
                    raise ExpressionCompileError(exp, 'unable to parse expression "{}"'.format(exp), col=e.col, original=e)

    @classmethod
    def get_new_expressions(cls):
        """Get new expressions added since last call to `get_new_expressions`"""
        expressions = [Expression(exp) for exp in cls.new_expressions]
        cls.new_expressions.clear()
        return expressions

    @classmethod
    def scan(cls, exp):
        """Parse as much of the string as possible, return a tuple containing
        the parsed string, and the unparsed string.

        """
        with cls._lock:
            scan = expr.scanString(exp, maxMatches=1)
            try:
                compiled_exp, start, end = next(scan)
            except StopIteration:
                return '', exp
            else:
                if start != 0:
                    return '', exp
                expression = exp[start:end]
                cls.exp_cache[expression] = compiled_exp.asList()
                return expression, exp[end:]

    _re_substitute_context = re.compile(r'\$\{(.*?)\}')

    @classmethod
    def extract(cls, text):
        """Extract and compile expression in substitution syntax"""
        text = text_type(text)
        if not text:
            return
        for exp in cls._re_substitute_context.findall(text):
            try:
                cls.compile_cache(exp.group(1))
            except:
                pass


class DefaultExpression(object):
    """An object that may be used where an Expression is used,
    but returns a pre-determined value.

    """
    return_value = None

    def __init__(self, return_value=Ellipsis):
        if return_value is not Ellipsis:
            self.return_value = return_value

    def __repr__(self):
        return 'DefaultExpression(%r)' % self.return_value

    def eval(self, context):
        return self.return_value


class TrueExpression(DefaultExpression):
    """A default expression that returns True"""
    def eval(self, context):
        return True


class FalseExpression(DefaultExpression):
    """A default expression that returns False"""
    def eval(self, context):
        return False


def main():
    from context import Context
    c = Context()
    c['foo'] = 5
    c['word'] = "apple"
    c["number"] = "100"
    c['bar'] = dict(a=2, b=3)

    def call(v):
        return v.split(',')
    c['filter'] = call

    e = Expression('upper:("Hello " + "World")', c)
    print(e())

    e = Expression('exists:"foo"', c)
    print(e())

    e = Expression('strip:last:("foo, bar, baz"|.filter)', c)
    print(e())

    e = Expression('"500" matches /\\d+/', c)
    print(e())

    e = Expression('not(1>1)', c)
    print(e())

    e = Expression('not ("500" matches /\\d+/)', c)
    print(e())

    e = Expression('bar["a"]', c)
    print(e())

    #c.push_frame('word')
#    from time import time
#    start = time()
#    e = c.compile("None")
#    print e()
    #for _ in xrange(10000):
    #    e()

if __name__=='__main__':
    #main()

    from moya.context import Context
    c = Context({'name': "Will"})
    c['.develop'] = True
    print(c.eval('{upper:name}'))

    print(c.eval('{upper:name}(name="will")'))

    exp = """list:map:[['one', 'two', 'three'], {upper:$$}]"""
    print(c.eval(exp))
