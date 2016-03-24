from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from ..elements.elementbase import (LogicElement,
                                    ReturnContainer,
                                    Attribute)
from ..context import Context, Expression
from ..context.expressiontime import ExpressionDateTime, TimeSpan
from ..context import dataindex
from ..context.errors import ContextKeyError
from ..containers import OrderedDict
from ..progress import Progress
from ..tools import make_cache_key
from .. import namespaces
from ..logic import (DeferNodeContents,
                     SkipNext,
                     Unwind,
                     EndLogic,
                     BreakLoop,
                     ContinueLoop,
                     MoyaException)
from ..console import style as console_style
from ..render import HTML
from ..html import escape as escape_html
from ..compat import zip_longest, raw_input, text_type, string, xrange, PY3

import json
import weakref
import getpass
import time
from collections import defaultdict
from datetime import datetime
from random import choice
from copy import copy

from time import sleep
from textwrap import dedent

import sys
import locale
import logging
log = logging.getLogger('moya.runtime')


try:
    import readline
except ImportError:
    pass


class ContextElementBase(LogicElement):
    pass


class If(ContextElementBase):
    """
    Conditional [i]IF[/i] tag, executes the enclosing block if a condition evaluates to [i]true[/i]. If the condition evaluates to [i]false[/i], the enclosing block is skipped. May be followed by [tag]else[/tag] or [tag]elif[/tag].

    """
    class Help:
        synopsis = """execute block if a condition is true"""
        example = """
        <if test="coffee==0">
            <echo>Get more coffee</echo>
        </if>"""

    test = Attribute("Test expression", required=True, metavar="CONDITION", type="expression")

    def logic(self, context):
        if self.test(context):
            yield DeferNodeContents(self)
            yield SkipNext((self.xmlns, "else"), (self.xmlns, "elif"))


class IfPost(ContextElementBase):
    """
    Executes the enclosing block if the current request is a POST request.

    Basically a shorthand for:

    [code xml]<if test=".request.method=='POST'">[/code]

    May be followed by [tag]else[/tag] or [tag]elif[/tag].

    """
    class Help:
        synopsis = """execute a block if this is a POST request"""
        example = """\
<if-post>
    <!-- validate form -->
</if-post>
<else>
    <!-- not a post request -->
</else>"""

    def logic(self, context):
        if context.get('.request.method', None) == 'POST':
            yield DeferNodeContents(self)
            yield SkipNext((self.xmlns, "else"), (self.xmlns, "elif"))


class IfGet(ContextElementBase):
    """
    Executes the enclosing block if the current request is a GET request.

    Basically a shorthand for:

    [code xml]<if test=".request.method=='GET'">[/code]

    May be followed by [tag]else[/tag] or [tag]elif[/tag].

    """
    class Help:
        synopsis = """exectute a block if this is a GET request"""

    def logic(self, context):
        if context.get('.request.method', None) == 'GET':
            yield DeferNodeContents(self)
            yield SkipNext((self.xmlns, "else"), (self.xmlns, "elif"))


class Else(ContextElementBase):
    """Execute the enclosed block if a previous [tag]if[/tag] statement is false."""

    class Help:
        synopsis = """execute a block if the previous <if> statement is false"""
        example = """
<if test="coffee==0">
    <echo>Get more coffee</echo>
</if>
<else>
    <echo>Have a cup of coffee</echo>
</else>

"""

    def logic(self, context):
        yield DeferNodeContents(self)


class Elif(ContextElementBase):
    """Executes the enclosed block if a previous [tag]if[/tag] (or [tag]elif[/tag]) statement is false, and another condition is true."""
    class Help:
        synopsis = """an <else> with a condition"""
        example = """\
<if test="hobbits == 0">
    <echo>There are no hobbits</echo>
</if>
<elif test="hobbits == 1">
    <echo>There is one hobbit</echo>
</elif>
<else>
    <echo>There are many hobbits</echo>
</else>
"""
    test = Attribute("Test expression", required=True, metavar="CONDITION", type="expression")

    def logic(self, context):
        if self.test(context):
            yield DeferNodeContents(self)
            yield SkipNext((self.xmlns, "else"), (self.xmlns, "elif"))


class Try(ContextElementBase):
    """Executes the enclosed block as part of a [tag]try[/tag][tag]catch[/tag] structure. """
    class Meta:
        is_try = True

    class Help:
        synopsis = """detect exceptions within a block"""
        example = """
<try>
    <echo>${1/0}</echo>  <!-- will throw a math exception -->
</try>
<catch exception="*">
    <echo>The try block threw an exception</echo>
</catch>
"""

    def logic(self, context):
        yield DeferNodeContents(self)


class ExceptionProxy(object):
    def __init__(self, msg, type, info):
        self.msg = msg
        self.type = type
        self.info = info

    def __repr__(self):
        return "<exception '{}'>".format(self.msg)


class Catch(ContextElementBase):
    """Catches any [link moyacode#exceptions]exceptions[/link] from the previous block."""

    class Help:
        synopsis = """catch exceptions from the previous block"""
        example = """
<try>
    <echo>${1/0}</echo>  <!-- will throw a math exception -->
</try>
<catch exception="math.divistion-error">
    <echo>The try block threw an exception</echo>
</catch>

<!-- A <try> block is only necessary if there are multiple statements you want to catch exceptions for -->
<echo>${1/0}<echo>
<catch exception="math.division-error">
    <echo>You can't divide by zero!</echo>
</catch>

        """

    exception = Attribute("Type of exception to catch", type="commalist", default="*", evaldefault=True)
    dst = Attribute("Destination to store exception object", type="reference")

    class Meta:
        logic_skip = True

    @classmethod
    def compare_exception(cls, type, catch_types):
        type_tokens = type.split('.')
        for catch_type in catch_types:
            for c, e in zip_longest(catch_type.split('.'),
                                    type_tokens,
                                    fillvalue=None):
                if c == '*':
                    return True
                if c != e:
                    break
            else:
                return True
        return False

    def check_exception_type(self, context, type):
        catch_type = self.exception(context)
        return self.compare_exception(type, catch_type)

    def set_exception(self, context, exception):
        dst = self.dst(context)
        if dst is not None:
            context[dst] = ExceptionProxy(exception.msg,
                                          exception.type,
                                          exception.info)


class Attempt(ContextElementBase):
    """Repeat a block of code if an exception is thrown. This is useful in situations where you are creating a database object
    with a random token, and you want to repeat the code if the random token happens to exist. The [c]wait[/c] attribute can set a timespan
    to wait between attempts, which may be appropriate for connecting to servers, for example.

    If an exception occurs, after [c]times[/c] attempts, then it will be thrown normally.

    [aside]Always set [c]times[/c] to a reasonable value. Programming errors could result in Moya getting stuck in a pointless loop.[/aside]

    """

    class Help:
        synopsis = """repeat a block until it is successful"""
        example = """
        <attempt times="10" catch="db.*">
            <db:create model="#ValidateEmail" let:user="user" dst="validate_email" />
        </attempt>

        """

    times = Attribute("Maximum number of times to repeat attempt block", type="integer", required=True)
    catch = Attribute("Type of exception to catch", type="commalist", default="*", evaldefault=True)
    wait = Attribute("Time to wait between syncs (default doesn't wait)", type="timespan", default=None, required=False)

    class Meta:
        trap_exceptions = True

    def on_exception(self, context, exception):
        stack = context.set_new_call('._attempt_stack', list)
        try:
            top = stack[-1]
        except IndexError:
            return None
        if not Catch.compare_exception(exception.type, top['type']):
            return None
        top['times'] -= 1
        if top['times'] > 0:
            if top['wait']:
                time.sleep(top['wait'])
            return DeferNodeContents(self)

    def logic(self, context):
        attempt_times = self.times(context)
        exception_type = self.catch(context)
        wait = self.wait(context)
        stack = context.set_new_call('._attempt_stack', list)
        stack.append({'times': attempt_times,
                      'type': exception_type,
                      'wait': wait})
        try:
            yield DeferNodeContents(self)
        except:
            stack.pop()


class With(ContextElementBase):
    """Merge values with the current scope in the enclosed block. The values in the let map will persist only in the enclosed block."""

    class Help:
        synopsis = """create a new data scope"""
        example = """
<with let:hobbit="Sam">
    <echo>${hobbit} is my favorite hobbit.
</with>
<!-- 'hobbit' will no longer exist at this point -->
<echo if="missing:hobbit">Where is the hobbit?</echo>

"""

    def logic(self, context):
        let_map = self.get_let_map(context)
        with context.data_scope(let_map):
            yield DeferNodeContents(self)


class DataSetterBase(ContextElementBase):
    default = None
    dst = Attribute("Destination", type="reference", default=None)

    class Help:
        undocumented = True

    def get_default(self):
        return self.default

    def set_context(self, context, dst, value):
        try:
            if dst is None:
                obj = context.obj
                append = getattr(obj, 'append', None)
                if append is not None:
                    append(value)
                    return text_type(len(obj) - 1)
                else:
                    return dst
            else:
                context[dst] = value
                return dst
        except ValueError as e:
            msg = "unable to set '{key}' to {value} ({e})"
            msg = msg.format(key=context.to_expr(dst),
                             value=context.to_expr(value),
                             e=text_type(e))
            self.throw('let.fail', msg)

    def logic(self, context):
        self.set_context(context,
                         self.dst(context),
                         self.get_value(context))

    def get_value(self, context):
        if self.text:
            return self.process_value(context, self.text)
        return self.default

    def process_value(self, context, value):
        return value


class DataSetter(DataSetterBase):
    default = None
    dst = Attribute("Destination", type="reference", default=None)
    value = Attribute("Value", type="expression", default=None)

    class Help:
        undocumented = True


class Var(DataSetter):
    """Set a variable"""

    class Help:
        synopsis = """create a value"""
        example = """
<var dst="count">10</var>
"""

    def logic(self, context):
        dst, value = self.get_parameters(context, 'dst', 'value')
        if not self.has_parameter('value'):
            value = context.eval(context.sub(self.text))
        self.set_context(context, dst, value)


class SetItem(LogicElement):
    """Set a value in a container"""

    class Help:
        synopsis = """set an indexed value on a collection"""
        example = """
        <dict dst="moya" />
        <set-item src="moya" index="'crew'" value="['john', 'rygel'] />
        """

    src = Attribute("collection object", type="expression", required=True)
    index = Attribute("index to set", type="expression", required=True)
    value = Attribute("value to set", type="expression", required=True)

    # TODO: handle errors
    def logic(self, context):
        src, index, value = self.get_parameters(context, 'src', 'index', 'value')
        src[index] = value


class Let(DataSetter):
    """Sets multiple variable from expressions."""

    class Help:
        synopsis = """create variables from expressions"""
        example = """
<let count="10" hobbit="'Sam'" hobbits="count * hobbit" />
        """

    class Meta:
        all_attributes = True

    _reserved_attribute_names = ['if']
    preserve_attributes = ['expressions']

    def post_build(self, context, _parse=dataindex.parse, _Expression=Expression, setter=Context.set, simple_setter=Context.set_simple):
        self.expressions = []
        append = self.expressions.append
        for k, v in self._attributes.items():
            if k not in self._reserved_attribute_names:
                indices = _parse(k)
                if indices.from_root or len(indices) > 1:
                    append((setter, indices, _Expression(v).eval))
                else:
                    append((simple_setter, indices.tokens[0], _Expression(v).eval))

    def logic(self, context):
        try:
            for setter, indices, _eval in self.expressions:
                setter(context, indices, _eval(context))
        except ContextKeyError as e:
            self.throw('let.fail',
                       text_type(e))


class LetParallel(Let):
    """
    Sets multiple variables in parallel.

    Like [tag]let[/tag], this tag sets values to the results of expressions, but evaluates all the expressions before assignment.

    One use for this, is to [i]swap[/i] variables without using an intermediate.
    """

    class Help:
        synopsis = """set values in parallel."""
        example = """
        <str dst="a">foo</str>
        <str dst="b">bar</str>
        <let-parallel a="b" b="a" />
        """

    class Meta:
        all_attributes = True

    _reserved_attribute_names = ['if']

    def logic(self, context):
        values = []
        for setter, indices, _eval in self.expressions:
            values.append(_eval(context))
        try:
            for (setter, indices, _eval), value in zip(self.expressions, values):
                setter(context, indices, value)
        except ContextKeyError as e:
            self.throw('let.fail',
                       text_type(e))


class LetStr(DataSetter):
    """Like [tag]let[/tag] but sets variables as strings. Setting strings with [tag]let[/tag] can look a little clumsy because of the requirement to escape the text twice. [tag]let-str[/tag] treats attributes as strings and not expressions."""

    class Help:
        synopsis = """create string variables"""
        example = """
<let-str hobbit="Sam" dwarf="Durin" />
"""

    class Meta:
        all_attributes = True

    _reserved_attribute_names = ['if']
    preserve_attributes = ['expressions']

    def post_build(self, context):
        self.expressions = []
        append = self.expressions.append
        for k, v in self._attributes.items():
            if k not in self._reserved_attribute_names:
                append((dataindex.parse(k), v))

    def logic(self, context):
        sub = context.sub
        for k, v in self.expressions:
            context[k] = sub(v)


class Int(DataSetter):
    """Set an integer value."""
    default = 0

    class Help:
        synopsis = """create an integer"""
        example = """
<int dst="count" value="10"/>
<int dst="position" /> <!-- defaults to 0 -->

"""

    def process_value(self, context, value):
        return int(value)

    def logic(self, context):
        dst, value = self.get_parameters(context, 'dst', 'value')
        if not self.has_parameter('value'):
            value = context.sub(self.text) or 0
        self.set_context(context,
                         dst,
                         int(value))


class Float(DataSetter):
    """Set a float value"""
    default = 0.0

    class Help:
        synopsis = """create a floating point value"""
        example = """
    <int dst="count" value="10"/>
    <int dst="position" /> <!-- defaults to 0.0 -->

    """

    def logic(self, context):
        dst, value = self.get_parameters(context, 'dst', 'value')
        if not self.has_parameter('value'):
            value = context.sub(self.text) or 0.0
        self.set_context(context,
                         dst,
                         float(value))


class Str(DataSetter):
    """Sets a string value to text contexts."""

    class Help:
        synopsis = """create a string"""
        example = """
<str dst="hobbit">Sam</str>
<str dst="text"/> <!-- defaults to empty string -->
"""

    default = ''
    value = Attribute("Value", type="expression", default=None)

    def get_value(self, context):
        if self.has_parameter('value'):
            return self.value(context)
        return context.sub(self.text)


class WrapTag(DataSetter):
    """Wraps text in a HTML tag."""

    class Help:
        synopsis = """wrap a string in a HTML tag"""
        example = """
        <!-- Wrap the string "Hello, World" in a P tag -->
        <wrap-tag tag="p" dst="paragraph">Hello, World!</wrap-tag>
        <echo>${paragraph}</echo>
        """

    tag = Attribute("Tag", default="span")

    def get_value(self, context):
        tag = self.tag(context)
        _let = self.get_let_map(context)
        if _let:
            attribs = " " + " ".join('{}="{}"'.format(k, escape_html(v)) for k, v in _let.items())
        else:
            attribs = ""
        return """<{tag}{attribs}>{text}</{tag}>""".format(tag=tag, attribs=attribs, text=escape_html(context.sub(self.text)))


class Dedent(DataSetter):
    """Removes common whitespace from the start of lines."""

    class Help:
        synopsis = """remove common whitespace from a string"""
        example = """
        <dedent dst="text">
            This text will have the initial whitespace removed
                This will start with only 4 spaces
            Back to column 0
        </dedent>
        """

    def get_value(self, context):
        text = context.sub(self.value(context) or self.text)
        dedent_text = dedent(text)
        return dedent_text


class HTMLTag(DataSetter):
    """Sets a variable to HTML."""

    class Help:
        synopsis = "create raw html"
        example = """
        <html dst="my_html"><![CDATA[
           <h1>Hello, World!</h1>
        ]]></html>
        """

    class Meta:
        tag_name = "html"

    def get_value(self, context):
        if self.has_parameter('value'):
            text = self.value(context)
        else:
            text = context.sub(self.text)
        return HTML(text)


# class GetLet(DataSetter):
#     """Retrieve the [i]let map[/i] of the enclosing tag."""

#     def get_value(self, context):
#         let_map = self.parent.get_let_map(context)
#         return let_map


# class RenderBBCode(DataSetter):
#     default = ''

#     def get_value(self, context):
#         from postmarkup import render_bbcode
#         return HTML(render_bbcode(context.sub(self.text)))


class _TimeSpan(DataSetter):
    """Create a datetime object"""

    class Help:
        synopsis = "create a timespan object"
        example = """
        <time-span dst="span" value="1d"/>
        """

    value = Attribute("Value", type="text", default="")

    def get_value(self, context):
        text = self.value(context) or context.sub(self.text)
        if not text:
            self.throw('time-span.invalid', "no timespan value specified")
        try:
            return TimeSpan(text)
        except ValueError as e:
            self.throw('time-span.invalid', text_type(e))


class Datetime(DataSetter):
    """
    Create a Moya [i]datetime[/i] object.

    Datetime objects have the following properties:

    [definitions]
        [define year]The year (integer)[/define]
        [define month]The month (integer) (1 is January)[/define]
        [define day]The day (integer)[/define]
        [define hour]The hours in the time[/define]
        [define minute]The number of minutes in the time[/define]
        [define second]The number of seconds in the time[/define]
        [define microseconds]The number of microseconds in the time[/define]
        [define isoformat]The date/time in [url http://en.wikipedia.org/wiki/ISO_8601]ISO 8601[/url] format[/define]
        [define next_day]The date/time + 24 hours[/define]
        [define previous_day]The date/time - 24 hours[/define]
        [define year_start]January 1st at the beginning of the year[/define]
        [define day_start]The beginning of the day (midnight)[/define]
        [define next_year]January 1st of the next year[/define]
        [define next_month]First day of the next month[/define]
        [define next_day]The start of the next day[/define]
        [define previous_day]The start of the previous day[/define]
        [define previous_year]Jan 1st of the previous year[/define]
        [define previous_monthy]First date of the previous month[/define]
        [define days_in_month]Number of days in the current month[/define]
        [define epoch]Number of seconds since Jan 1st 1970[/define]
        [define html5_datatime]Date/Time in HTML5 format[/define]
        [define html5_data]Date in HTML5 format[/define]
        [define html_time]Time in HTML5 format[/define]
        [define utc]Date/Time in UTC timezone[/define]
        [define local]DateTime in local timezone (references [c].tz[/c])[/define]
    [/definitions]

    """

    class Help:
        synopsis = """create a date/time object"""
        example = """
        <datetime year="1974" month="7" day="5" dst="birthday" />
        <echo>Your birthday is ${localize:birthday}</echo>
        """

    year = Attribute("Year", type="integer", required=True)
    month = Attribute("Month", type="integer", required=False, default=1)
    day = Attribute("Month", type="integer", required=False, default=1)
    hour = Attribute("Hour", type="integer", required=False, default=0)
    minute = Attribute("Minute", type="integer", required=False, default=0)
    second = Attribute("Second", type="integer", required=False, default=0)

    def get_value(self, context):
        try:
            return ExpressionDateTime(*self.get_parameters(context,
                                                           "year",
                                                           "month",
                                                           "day",
                                                           "hour",
                                                           "minute",
                                                           "second"))
        except Exception as e:
            self.throw("datetime.invalid", text_type(e))


class Bool(DataSetter):
    """Create a boolean (True or False value)."""

    class Help:
        synopsis = """create a boolean"""
        example = """
        <bool dst="bool"/> <!-- False -->
        <bool dst="bool">yes</bool> <!-- True -->
        <bool dst="bool">no</bool> <!-- False -->
        <bool dst="bool" value="1"/> <!--True -->
        <bool dst="bool" value="0"/> <!-- False -->
        """

    default = False

    def logic(self, context):
        if self.text:
            value = self.text.lower() in ('yes', 'true')
        else:
            value = self.value(context)
        self.set_context(context,
                         self.dst(context),
                         bool(value))


class True_(DataSetter):
    """Creates a boolean with a value of True."""

    class Help:
        synopsis = """create a True boolean"""
        example = """
        <true dst="bool"/> <!-- Always True -->
        """

    default = True

    def get_value(self, context):
        return True


class False_(DataSetter):
    """Creates a boolean with a value of False."""

    class Help:
        synopsis = """create a False boolean"""
        example = """
        <false dst="bool"/> <!-- Always False -->
        """
    default = False

    def get_value(self, context):
        return False


class None_(DataSetter):
    """Create a None value."""

    class Help:
        synopsis = """Create a value of None"""
        example = """
        <none dst="hobbits"/>
        <echo>Hobbits in England: ${hobbits}</echo>
        """

    default = None

    def get_value(self, context):
        return None


class Now(DataSetter):
    """Create a datetime objects for the current time. The datetime is in UTC, use the [c]localize:[/c] modifier to display a time in the user's current timezone."""

    class Help:
        synopsis = """get the current date/time"""
        example = """
        <now dst="now" />
        <echo>The time is ${localize:now}</now>
        """

    def logic(self, context):
        self.set_context(context,
                         self.dst(context),
                         datetime.utcnow())


class List(DataSetter):
    """Creates a list. Any data items in the enclosed block are added to the list."""

    class Help:
        synopsis = """create a list"""
        example = """
        <list dst="hobbits">
            <str>Sam</str>
            <str>Bilbo</str>
            <str>Frodo</str>
        </list>
        <echo>${commalist:hobbits}</echo>
        <list dst="empty"/>
        """

    def logic(self, context):
        dst = self.set_context(context, self.dst(context), [])
        context.push_scope(dst)
        try:
            yield DeferNodeContents(self)
        finally:
            context.pop_scope()


class Lines(DataSetter):
    """
    Create a list from lines.

    This tag create a list of strings from the lines in the enclosed text. Lines are striped of whitespace.

    The following two examples are equivalent:

    [code python]
    <list dst="hobbits">
        <str>Sam</str>
        <str>Bilbo</str>
        <str>Frodo</str>
    </list>
    [/code]
    [code]
    <lines dst="hobbits">
        Sam
        Bilbo
        Frodo
    </lines>
    [/code]
    """

    class Help:
        synopsis = """create a list from lines"""
        example = """
        <lines dst="hobbits">
            Sam
            Bilbo
            Frodo
        </lines>
        """

    def get_value(self, context):
        return [s.strip() for s in context.sub(self.text).strip().splitlines()]


class Sum(DataSetter):
    """Sums a sequence of values together."""

    class Help:
        synopsis = """sums a sequence of values"""
        example = """
        <sum dst="moluae">
            <int>2</int>
            <int>40</int>
        </sum>
        <echo>${moluae}</echo>
        """

    def logic(self, context):
        container = []
        list_index = self.set_context(context, self.dst(context), container)
        context.push_scope(list_index)
        try:
            yield DeferNodeContents(self)
        finally:
            context.pop_scope()
        self.set_context(context, self.dst(context), sum(container))


class AppendableSet(set):
    """A set with an 'append' method that is an alias for 'add'"""
    def append(self, value):
        return self.add(value)


class Set(DataSetter):
    """Create a [i]set[/i] object. A set is a container, where each item may only appears once. Any data items in the enclosed block are added to the set."""

    class Help:
        synopsis = """create a set object"""
        example = """
        <set dst="hobbits">
            <str>Sam</str>
            <str>Bilbo</str>
            <str>Frodo</str>
            <str>Bilbo</str>
            <str>Sam</str>
        </set>
        <!-- Will display 3, because duplicates are removed -->
        <echo>There are ${len:hobbits} in the set.</echo>

        """

    def logic(self, context):
        dst = self.set_context(context, self.dst(context), AppendableSet())
        context.push_scope(dst)
        try:
            yield DeferNodeContents(self)
        finally:
            context.pop_scope()


class Dict(DataSetter):
    """Create a [i]dictionary[/i] object. A dictionary maps [i]keys[/i] on to [i]values[/i]. The keys and values are defined in the enclosing block, or via the [i]let map[/i]."""

    class Help:
        synopsis = """create a dict object"""
        example = """
        <dict dst="species">
            <str dst="Bibo">Hobbit</dst>
            <str dst="Gandalph">Wizard</dst>
        </dict>
        <!-- Alternatively -->
        <dict dst="species" let:Bilbo="Hobbit" let:Gandalph="Wizard" />
        <echo>Bilbo is a ${species['Bilbo']}</echo>

        """

    default = Attribute("Default return for missing keys", type="expression", required=False, default=None)
    sequence = Attribute("Optional sequence of key / value pairs to initialize the dict", type="expression", required=False)

    _default_types = {'dict': OrderedDict,
                      'list': list,
                      'int': int,
                      'float': float}

    def logic(self, context):
        sequence = self.sequence(context)
        if self.has_parameter('default'):
            default = self.default(context)
            obj = defaultdict(lambda: copy(default))
        else:
            obj = {}
        # default = self.default(context)
        # if default is None:
        #     obj = {}
        # else:
        #     obj = defaultdict(self._default_types[default])
        obj.update(self.get_let_map(context))
        if sequence:
            obj.update(sequence)
        dst = self.set_context(context,
                               self.dst(context),
                               obj)

        with context.scope(dst):
            yield DeferNodeContents(self)


class Unpack(DataSetter):
    """Unpack the keys and values in an object, and set them on the parent"""

    obj = Attribute("Object to unpack", type="expression")

    def logic(self, context):
        obj = self.obj(context)
        try:
            items = obj.items()
        except:
            self.throw('bad-value.map-required',
                       'a dict or other mapping is required for obj')
        for k, v in items:
            self.set_context(context, context.escape(k), v)


class MakeToken(DataSetter):
    """Generates a token of random characters. This is useful for creating unique IDs for database objects."""

    class Help:
        synopsis = """make an opaque token"""
        example = """
        <maketoken dst="authorization_token" size="16" />
        """

    lowercase = Attribute("Use lower case characters", type="boolean", default=True, required=False)
    uppercase = Attribute("Use upper case characters", type="boolean", default=True, required=False)
    digits = Attribute("Use digits", type="boolean", default=True, required=False)
    punctuation = Attribute("Use punctuation", type="boolean", default=False, required=False)
    size = Attribute("Size", type="integer", default=20, required=False)

    def get_value(self, context):
        (size,
         lowercase,
         uppercase,
         digits,
         punctuation) = self.get_parameters(context,
                                            "size",
                                            "lowercase",
                                            "uppercase",
                                            "digits",
                                            "punctuation")
        choices = ""
        if lowercase:
            choices += string.lowercase
        if uppercase:
            choices += string.uppercase
        if digits:
            choices += string.digits
        if punctuation:
            choices += string.punctuation
        if not choices:
            self.throw("token", "No characters to choice from")
        token = ''.join(choice(choices) for _ in xrange(size))
        return token


class ODict(Dict):
    """Like <dict> but creates an [i]ordered[/i] dictionary (maintains the order data was inserted)/"""

    def logic(self, context):
        dst = self.set_context(context,
                               self.dst(context),
                               OrderedDict(self.get_let_map(context)))
        context.push_scope(dst)
        yield DeferNodeContents(self)


class Throw(Dict):
    """Throw a Moya exception. An exception consists of a name in dotted notation with an optional message.

    Custom exceptions should be named to start with the [i]long name[/i] of the library. Moya reserves exceptions with a single dot for internal use. These [i]may[/i] be thrown if appropriate.

    """

    class Help:
        synopsis = """throw an exception"""
        example = """
        <try>
            <throw exception="middle.earth.cant" msg="One can't simply do that!"/>
        </try>
        <except exception="middle.earth.*" dst="error">
            <echo>Error: ${error.msg}</echo>
        </except>

        """

    exception = Attribute("Type of exception", required=True)
    msg = Attribute("Message", default="exception thrown", required=False)

    def logic(self, context):
        exception, msg = self.get_parameters(context, 'exception', 'msg')
        info = context['_e'] = {}
        with context.scope('_e'):
            yield DeferNodeContents(self)
        raise MoyaException(exception, msg, info)


class Choose(DataSetter):
    """Pick a random element from a sequence."""

    class Help:
        synopsis = """choose a random value from a collection"""
        example = """
        <choose dst="hobbit" from="['bilbo','sam','frodo']"/>
        <echo>Hobbit: ${hobbit}</echo>
        """
    _from = Attribute("Container", required=True, type="expression")
    dst = Attribute("Destination", default=None, metavar="DESTINATION", type="reference", required=True)

    def logic(self, context):
        _from, dst = self.get_parameters(context, 'from', 'dst')
        self.set_context(context, dst, choice(_from))


class JSON(DataSetter):
    """Sets data from JSON (JavasSript Object Notation)."""

    src = Attribute("JSON source", type="expression", required=False)

    class Help:
        synopsis = """create data from JSON"""
        example = """
        <json dst="hobbits">
            ["Bilbo", "Sam", "Frodo"]
        </json>

        """

    def logic(self, context):
        self.set_context(context,
                         self.dst(context),
                         self.get_value(context))

    def get_value(self, context):
        if self.has_parameter('src'):
            text = self.src(context)
        else:
            text = self.text
        try:
            return json.loads(text)
        except Exception as e:
            self.throw('json.invalid', text_type(e))


# class UpdateURLquery(DataSetter):
#     """Update the query portion of a URL with data from the [i]let map[/i]."""

#     url = Attribute("URL", required=True)

#     def logic(self, context):
#         url = self.url(context)

#         parsed_url = urlparse(url)

#         url_query = parsed_url.query
#         query_components = parse_qs(url_query)
#         query_components.update(self.get_let_map(context))

#         url = urlunparse((parsed_url.scheme,
#                           parsed_url.netloc,
#                           parsed_url.path,
#                           parsed_url.params,
#                           urlencode(query_components, True),
#                           parsed_url.fragment))
#         self.set_context(context,
#                          self.dst(context),
#                          url)


class Slice(ContextElementBase):
    """Slice a sequence of values (extract a range of indexed values)."""

    class Help:
        synopsis = """get a 'slice' of a collection"""
        example = """
        <slice src="hobbits" start="1" stop="3" dst="slice_of_hobbits"/>

        """

    src = Attribute("Value to slice", required=True, type="reference", metavar="ELEMENTREF")
    dst = Attribute("Destination for slice", required=True, type="reference", metavar="ELEMENTREF")
    start = Attribute("Start point", type="expression", default=None)
    stop = Attribute("End point", type="expression", default=None)

    def logic(self, context):
        src, dst, start, stop = self.get_parameters(context, 'src', 'dst', 'start', 'stop')
        src_obj = context[src]

        if hasattr(src_obj, 'slice'):
            context[dst] = src_obj.slice(start or 0, stop)
        else:
            context[dst] = src_obj[start:stop]


class Page(ContextElementBase):
    """Chop a sequence in to a [i]page[/i].

    This breaks up a sequence in to a page, based on a page size and index. Useful for paginating search results.
    """

    class Help:
        synopsis = """get a page of results"""
        example = """
        <page src="results" page="2" pagesize="10" />
        """

    src = Attribute("Value to slice", required=True, type="reference", metavar="ELEMENTREF")
    dst = Attribute("Destination for slice", required=True, type="reference", metavar="ELEMENTREF")
    page = Attribute("Page", type="expression", required=False, default=".request.GET.page or 1", evaldefault=True)
    pagesize = Attribute("Page size", type="expression", required=False, default=10)

    def logic(self, context):
        src, dst, page, pagesize = self.get_parameters(context, 'src', 'dst', 'page', 'pagesize')
        try:
            page = int(page or 1)
        except ValueError:
            page = 1
        start = (page - 1) * pagesize
        stop = page * pagesize
        src_obj = context[src]
        if hasattr(src_obj, 'slice'):
            context[dst] = src_obj.slice(start, stop)
        else:
            context[dst] = src_obj[start:stop]


class Inc(ContextElementBase):
    """Increment (add 1 to) a value."""

    class Help:
        synopsis = """increment a value"""
        example = """
        <let hobbit_count="1" />
        <inc dst="hobbit_count" />
        <echo>${hobbit_count}</echo> <!-- 2 -->
        """

    dst = Attribute("Value to increment", required=True, type="reference", metavar="ELEMENTREF")

    def logic(self, context):
        try:
            context[self.dst(context)] += 1
        except:
            self.throw('inc.fail',
                       'unable to increment')


class Dec(ContextElementBase):
    """Decrement (subtract 1 from) a value."""

    class Help:
        synopsis = """decrement a value"""
        example = """
        <let hobbit_count="2" />
        <dec dst="hobbit_count" />
        <echo>${hobbit_count}</echo> <!-- 1 -->
        """
    dst = Attribute("Value to decrement", required=True, type="reference")

    def logic(self, context):
        try:
            context[self.dst(context)] -= 1
        except:
            self.throw('dec.fail',
                       'unable to decrement')


class Copy(ContextElementBase):
    """Copy a variable from one location to another"""

    class Help:
        synopsis = """copy a value"""
        example = """
        <str dst="foo">Kirk</str>
        <copy src="foo" dst="bar" />
        <echo>${bar}</echo>
        """

    src = Attribute("Source", required=True, type="reference")
    dst = Attribute("Destination", required=True, type="reference")

    def logic(self, context):
        context.copy(*self.get_parameters(context, 'src', 'dst'))


class Link(ContextElementBase):
    """Create a [i]link[/i] in the context. Similar to a symlink in the filesystem, a link creates a variable that references another value."""

    class Help:
        synopsis = """link variables"""
        example = """
        <str dst="foo">Hello</str>
        <link src="foo" dst="bar" />
        <str dst="bar">World</str>
        <echo>${foo}</bar> <!-- World -->
        <echo>${bar}</bar> <!-- World -->

        """

    src = Attribute("Source", required=True, type="reference")
    dst = Attribute("Destination", required=True, type="reference")

    def logic(self, context):
        context.link(*self.get_parameters(context, 'dst', 'src'))


class Append(ContextElementBase):
    """Append a value to a list or other collection."""

    class Help:
        synopsis = """append a value to a list"""
        example = """
        <list dst="crew">
            <str>John</str>
        </list>
        <append src="crew" value="'Scorpius'"/>
        """

    class Meta:
        one_of = [('value', 'values')]

    value = Attribute("Value to append", type="expression", missing=False, required=False)
    values = Attribute("A sequence of values to append", type="expression", missing=False, required=False)
    src = Attribute("Collection to append to", type="expression", required=True, missing=False)

    def logic(self, context):
        value, values, src = self.get_parameters(context, 'value', 'values', 'src')
        if self.has_parameter('value'):
            values = [value]
        for v in values:
            try:
                src.append(v)
            except:
                if not hasattr(src, 'append'):
                    self.throw("bad-value.not-supported",
                               "src does not support append operation",
                               diagnosis="Not all objects may be appended to, try using a list or list-like object.")
                else:
                    self.throw("append.fail",
                               "unable to append",
                               diagnosis="Check the value you are appending is the type expected.")


class Remove(ContextElementBase):
    """Remove a value from a collection"""

    class Help:
        synopsis = """remove a value from a collection"""
        example = """
        <list dst="crew">
            <str>John</str>
            <str>Scorpius/str>
        </list>
        <remove src="crew" value="'Scorpius'"/>
        """

    class Meta:
        one_of = [('value', 'values')]

    value = Attribute("Value to remove", type="expression", missing=False, required=False)
    values = Attribute("A sequence of values to remove", type="expression", missing=False, required=False)
    src = Attribute("Collection to remove from", type="expression", required=True, missing=False)

    def logic(self, context):
        value, values, src = self.get_parameters(context, 'value', 'values', 'src')
        if value is not None:
            values = [value]
        for v in values:
            try:
                src.remove(v)
            except ValueError:
                # removing non-existent value is a nop
                continue
            except:
                if not hasattr(src, 'remove'):
                    self.throw("bad-value.not-supported",
                               "src does not support remove operation")
                else:
                    self.throw("remove.fail",
                               "unable to remove")


class Extend(ContextElementBase):
    """Extend a sequence with values from another sequence."""

    class Help:
        synopsis = """add values from one sequence to another"""
        example = """
        <list dst="crew">
            <str>John</str>
        </list>
        <extend dst="crew" src="['Scorpius', 'Aeryn']"/>
        """

    src = Attribute("Collection to append to", type="expression")
    values = Attribute("value(s) to extend with", type="reference")

    def logic(self, context):
        src, values = self.get_parameters(context, 'src', 'values')
        try:
            src.extend(values)
        except:
            if not hasattr(src, 'extend'):
                self.throw('bad-value.not-supported',
                           'src does not support extend')
            else:
                self.throw('extend.fail',
                           'unable to extend')


class Update(ContextElementBase):
    """Update a dictionary (or other mapping collection) with keys and values from another dictionary."""

    class Help:
        synopsis = """add new values to a dictionary"""
        example = """
        <dict dst="species"/>
        <update dst="species" src="john='human', scorpius='unknown'"/>
        """

    src = Attribute("Collection to update", type="expression")
    values = Attribute("Values to update with", type="expression")

    def logic(self, context):
        src, values = self.get_parameters(context, 'src', 'values')

        try:
            src.update(values)
        except:
            if not hasattr(src, 'update'):
                self.throw('bad-value.not-supported',
                           "src does not support update")
            else:
                self.throw('update.fail',
                           'failed to update')


class Pop(DataSetter):
    """Remove and return a value from a dictionary."""

    class Help:
        synopsis = """remove a value from a dictionary"""
        example = """
        <dict dst="species">
            <let john="human"/>
            <let scorpius="unknown"/>
        </dict>
        <pop src="species" key="scorpius" dst="scorpius_species"/>
        <echo>${scorpius_species}</echo> <!-- "unknown" -->
        """

    src = Attribute("Source", type="expression")
    dst = Attribute("Destination", type="reference", required=False, default=None)
    key = Attribute("Key", type="expression", required=False)

    def logic(self, context):
        src, dst, key = self.get_parameters(context, 'src', 'dst', 'key')
        try:
            if self.has_parameter('key'):
                value = src.pop(key)
            else:
                value = src.pop()
        except IndexError:
            self.throw('pop.empty',
                       "can't pop from an empty list")
        except:
            self.throw('pop.fail',
                       'unable to pop from src')

        if dst is not None:
            self.set_context(context, dst, value)


class Echo(ContextElementBase):
    """Write text to the console. This is typically used in commands or for debugging. Bear in mind that in a production environment there is no console."""

    class Help:
        synopsis = """write text to the console"""
        example = """<echo>Hello, World</echo>"""

    obj = Attribute("If given, then the value of this expression will be written to the console",
                    type="expression", required=False, default=None)
    table = Attribute("A table to display. If given this value should be a list of lists.", type="expression", required=False, default=None)
    header = Attribute("A list of headers for the table (if given)", type="commalist", required=False, default=None)
    indent = Attribute("Number of indents", type="expression", required=False, default=0)
    style = Attribute("Console style", required=False, default="bold cyan")

    def logic(self, context):
        obj = self.obj(context)
        tabs = self.indent(context)
        table = self.table(context)
        header = self.header(context)
        style = console_style(self.style(context))
        console = context.root.get('console', None)
        if console is None:
            from .. import pilot
            console = pilot.console
        if self.archive.debug_echo:
            line_msg = '[file "{}", line {}]\n'.format(self._location, self.source_line)
            console(line_msg, fg="yellow")
        if self.has_parameter('table'):
            console.table(table, header_row=header)
        else:
            if obj is not None:
                console.obj(context, obj, **style)
            else:
                console.text(context.sub(("    " * tabs) + self.text), **style)


class Exit(ContextElementBase):
    """Exit the current command. When Moya sees this tag it stops running the current command and returns an exit code. It will also write any enclosed text to the console."""

    class Help:
        synopsis = """exit the current command"""
        example = """<exit code="-5" if="not continue">User cancelled</exit>"""

    code = Attribute("Return code", type="expression", default=0, map_to="exit_code")

    def logic(self, context):
        exit_code = self.exit_code(context)
        if self.text.strip():
            context.root['console'].text(context.sub(self.text.strip()), fg="cyan", bold=True)
        raise EndLogic(exit_code)


class Debug(ContextElementBase):
    """Executes a block only if Moya is in debug mode. You can enable debug mode the setting 'debug' under the project section. This tag is equivalent to the following:

[code xml]
<if test=".debug">
    <echo>Moya is in debug mode. Relax.</echo>
</if>
[/code]

[alert]Be careful to not do anything inside this tag that your project may depend on. It will not execute in a production environment![/alert]

    """

    class Help:
        synopsis = """execute debug code"""
        example = """
        <debug>
            <echo>Moya is in debug mode. Relax.</echo>
        </debug>
        """

    def logic(self, context):
        if context.get('.debug', False):
            yield DeferNodeContents(self)


class For(ContextElementBase):
    """Execute a block of code for each value in a sequence. This tag [i]iterates[/i] over a sequence, and executes the enclosed block for each value."""

    class Help:
        synopsis = "iterate over a sequence"
        example = """
        <for src="['John', 'Scorpius', 'Rygel']" dst="crew_member" filter="crew_member != 'Rygel'">
            <echo>${crew_member} is on board!</echo>
        </for>

        """

    class Meta:
        is_loop = True

    src = Attribute("Source sequence", required=True, type="expression")
    dst = Attribute("Destination value", required=True, type="commalist")
    filter = Attribute("If given, then only those values which match this condition will cause the enclosed block to execute.",
                       required=False, type="expression", default=True)

    def logic(self, context, _defer=DeferNodeContents):
        objects, dst = self.get_parameters(context, 'src', 'dst')

        filter = self.filter
        try:
            iter_objects = iter(objects)
        except TypeError:
            self.throw("bad-value.not-iterable", "source is not iterable")
        else:
            if len(dst) == 1:
                dst = dst[0]
                for obj in iter_objects:
                    context[dst] = obj
                    if filter(context):
                        yield _defer(self)
            else:
                for obj in iter_objects:
                    try:
                        for set_dst, set_value in zip(dst, obj):
                            context[set_dst] = set_value
                    except TypeError:
                        self.throw("bad-value.not-iterable", "Object in sequence does not support iteration")
                    if filter(context):
                        yield _defer(self)


class Switch(ContextElementBase):
    """
    Jump to a location with in a code block, based in an input value.

    This tag takes a value ([c]on[/c]) and jumps to a [tag]case[/tag] in the enclosed block that has a matching value.
    If there is no matching [tag]case[/tag], then execution will move to the enclosed [tag]default-case[/tag]. If no default case exists, the entire block is skipped.

    This tag is useful in situations where a chain of [tag]if[/tag] and [tag]elif[/tag] tags would otherwise be used. Here's an example:

    [code xml]
    <switch on="species">
        <case>human</case>
        <echo>Humans come from Earth</echo>

        <case>hynerian</case>
        <echo>Hynerians come from Hyneria</echo>

        <default-case/>
        <echo>I have no idea where ${species}s come from</echo>
    </switch>
    [/code]

    The above code is equivalent to the following:

    [code xml]
    <if test="species=='human'">
        <echo>Humans come from Earth</echo>
    </if>
    <elif test="species=='hynerian'">
        <echo>Hynerians come from Hyneria</echo>
    </elif>
    <else>
        <echo>I have no idea where ${species}s come from</echo>
    </else>
    [/code]

    The [tag]switch[/tag] version is generally clearer, especially with a large number of conditions.

    If the [c]on[/c] attribute is [i]not[/i] given, then the case's [c]if[/c] attribute is checked. Here's the previous example, implemented without the [c]on[/c] attribute:

    [code xml]
    <switch>
        <case if="species=='human'"/>
        <echo>Humans come from Earth</echo>

        <case if="species=='hynerian'"/>
        <echo>Hynerians come from Hyneria</echo>

        <default-case/>
        <echo>I have no idea where ${species}s come from</echo>
    </switch>
    [/code]

    """

    class Help:
        synopsis = "jump to matching case"

    class Meta:
        is_loop = True

    on = Attribute("Value to test", type="expression", required=False)

    def logic(self, context):
        case_tags = [(namespaces.default, 'case'), (namespaces.default, 'default-case')]

        if self.has_parameter('on'):
            switch_on = self.on(context)
            iter_children = iter(self)
            while 1:
                child = next(iter_children, None)
                if child is None:
                    return
                if child._element_type in case_tags and child.test(context, switch_on):
                    for child in iter_children:
                        yield child
                    break
        else:
            iter_children = iter(self)
            while 1:
                child = next(iter_children, None)
                if child is None:
                    return
                if child._element_type in case_tags and child._if(context):
                    for child in iter_children:
                        yield child
                    break


class Case(ContextElementBase):
    """
    Defines a case in a [tag]switch[/tag] tag.

    If a [c]value[/c] attribute is given, it will be used as the comparison values, otherwise the tag text will be used.

    """

    class Help:
        synopsis = "define a case in a switch"

    value = Attribute("Value to compare in a switch", type="expression", required=False)

    def check(self, context):
        return True

    def test(self, context, switch_value):
        if self.has_parameter('value'):
            value = self.value(context)
        else:
            value = context.sub(self.text.strip())
        return value == switch_value

    def logic(self, context):
        raise BreakLoop()


class DefaultCase(ContextElementBase):
    """
    Defines the [i]default[/i] case in a [tag]switch[/tag] tag.

    """

    class Help:
        synopsis = "default case in a switch"

    def check(self, context):
        return True

    def test(self, context, switch_value):
        return True

    def logic(self, cotnext):
        raise BreakLoop()


class ProgressElement(ContextElementBase):
    """Like a for loop but renders an ascii progress bar in the console, which will look something like the following:

    [code]
    [###        ] 30% working...
    [/code]

    This is useful for commands that may take some time to execute.

    """

    class Help:
        synopsis = """render an ascii progress bar"""

    src = Attribute("Source", required=True, type="expression")
    dst = Attribute("Destination", required=True, type="commalist")
    filter = Attribute("If given, then only those values which match this condition will cause the enclosed block to execute.",
                       required=False, type="expression", default=True)

    msg = Attribute("Message on progress bar", required=False, default="working...")
    steps = Attribute("Number of steps in the sequence", required=False, type="integer")

    class Meta:
        tag_name = "progress"
        is_loop = True

    def logic(self, context):
        objects, dst, msg, steps = self.get_parameters(context, 'src', 'dst', 'msg', 'steps')
        console = context.root['console']

        if steps is None:
            try:
                steps = len(objects)
            except:
                self.throw('moya.progress.no-length',
                           "Unable to get length of {!r}".format(objects))

        filter = self.filter

        progress = Progress(console, msg, width=20, num_steps=steps)
        context['.progress'] = progress
        progress.render()

        try:
            iter_objects = iter(objects)
        except TypeError:
            self.throw("bad-value.not-iterable", "Source is not iterable")
        else:
            msg = self.msg(context)
            try:
                console.show_cursor(False)
                if len(dst) == 1:
                    dst = dst[0]
                    for obj in iter_objects:
                        context[dst] = obj
                        progress.step()
                        if filter(context):
                            yield DeferNodeContents(self)
                else:
                    for obj in iter_objects:
                        try:
                            for set_dst, set_value in zip(dst, obj):
                                context[set_dst] = set_value
                        except TypeError:
                            self.throw("bad-value.not-iterable",
                                       "Object in sequence does not support iteration")
                        if filter(context):
                            yield DeferNodeContents(self)
                        progress.step()
            finally:
                console.show_cursor(True)
                progress.done()


class ProgressMsg(ContextElementBase):
    """
    Set a progress message.

    Must appear inside a [tag]progress[/tag] tag.

    """

    class Help:
        synopsis = "set a progress message"
        example = """
        <progress-msg>reading post ${post}</progress-msg>
        """

    def logic(self, context):
        msg = context.sub(self.text)
        context['.progress.msg'] = msg


class Sleep(ContextElementBase):
    """Do nothing for a period of time"""

    class Help:
        synopsis = """wait for while"""
        example = """<sleep for="10s"/> <!-- do nothing for 10 seconds -->"""

    _for = Attribute("Amount of time to sleep for", required=True, type="timespan")

    def logic(self, context):
        t = self.get_parameter(context, 'for')
        sleep(float(t))


class Map(DataSetter):
    """Create a list by mapping an expression on to a sequence"""

    class Help:
        synopsis = "map an expression on to sequence"
        example = """
        <list dst="crew">
            <dict let:name="'john'" let:species="'human'" />
            <dict let:name="'rygel'" let:species="'hynerian'" />
            <dict let:name="'aeryn'" let:species="'peacekeeper'" />
        </list>
        <map src="crew" dst="manifest"
            value="sub:'${title:name} is ${species}'" />
        <!-- ['John is human', 'Rygen is hynerian', 'Aeryn is peacekeeper'] -->
        """

    src = Attribute("Source sequence", required=True, type="expression")
    dst = Attribute("Destination", required=False, type="reference")
    value = Attribute("Expression", required=True, type="function")
    _filter = Attribute("Skip item if this expression is false", required=False, type="function")

    def get_value(self, context):
        objects, dst, func, _filter = self.get_parameters(context, 'src', 'dst', 'value', 'filter')
        func = func.get_scope_callable(context)
        if _filter is None:
            result = [func(obj) for obj in objects]
        else:
            _filter = _filter.get_scope_callable(context)
            result = [func(obj) for obj in objects if _filter(obj)]

        return result


class Group(DataSetter):
    """
    Group a sequence in to a list of values with common keys.

    """

    class Help:
        synopsis = "group a sequence by common keys"
        example = """
        <list dst="crew">
            <dict let:name="'Rygel'" let:species="'hynerian'" />
            <dict let:name="'Aeryn'" let:species="'peacekeeper'" />
            <dict let:name="'Jothee'" let:species="'luxan'" />
            <dict let:name="'D\'Argo'" let:species="'luxan'" />
        </list>
        <group src="crew" key="species" value="name" dst="by_species" />
        <!-- {'hynerian': ['Rygel'], 'peacekeeper': ['Aeryn'], 'luxan': ['Jothee', 'D\'Argo']} -->

        """

    src = Attribute("Source sequence", required=True, type="expression")
    dst = Attribute("Destination", required=False, type="reference")
    key = Attribute("Key", required=True, type="function")
    value = Attribute("Expression", required=False, type="function", default="$$", evaldefault=True)

    def get_value(self, context):
        result = OrderedDict()
        objects, dst, _key, _value = self.get_parameters(context, 'src', 'dst', 'key', 'value')
        key_func = _key.get_scope_callable(context)
        value_func = _value.get_scope_callable(context)
        for obj in objects:
            key = key_func(obj)
            value = value_func(obj)
            result.setdefault(key, []).append(value)
        return result


class MapDict(DataSetter):
    """Create a list of dictionaries from a sequence."""

    class Help:
        synopsis = "generate a list of dictionaries"
        example = """
        <list dst="crew">
            <dict let:name="'john'" let:species="'human'" />
            <dict let:name="'rygel'" let:species="'hynerian'" />
            <dict let:name="'aeryn'" let:species="'peacekeeper'" />
        </list>
        <map-dict src="crew" dst="crew" let:name="title:name" let:human="species == 'human'"/>
        <!-- [{'name':John, 'human':yes}, {'name':Rygel, 'human':no}, {'name':'Aeryn',  'human':no}] -->
        """

    src = Attribute("Source sequence", required=True, type="expression")
    dst = Attribute("Destination", required=False, type="reference")
    _filter = Attribute("Skip item if this expression is false", required=False, type="function")

    def logic(self, context):

        objects, dst, _filter = self.get_parameters(context, 'src', 'dst', 'filter')

        if _filter is None:
            predicate = lambda obj: True
        else:
            predicate = _filter.get_scope_callable(context)

        map_result = []
        for obj in objects:
            with context.data_scope(obj):
                if not predicate(obj):
                    continue
                value = self.get_let_map(context)
                with context.data_scope(value):
                    yield DeferNodeContents(self)
                map_result.append(value)
        self.set_context(context,
                         dst,
                         map_result)


class Max(DataSetter):
    """Get the maximum value in a sequence."""

    class Help:
        synopsis = "get the maximum value in a sequence"

    src = Attribute("Source sequence", required=True, type="expression")
    key = Attribute("Key", type="function", required=False, default=None, missing=False)

    def logic(self, context):
        objects, dst, key = self.get_parameters(context, 'src', 'dst', 'key')
        if not objects:
            self.throw('max.empty', 'src is empty', diagnosis="Moya can't calculate the maximum of an empty sequence.")
        if key is None:
            result = max(objects)
        else:
            key_callable = key.get_scope_callable(context)
            result = max(key_callable(obj) for obj in objects)
        self.set_context(context, dst, result)


class Min(DataSetter):
    """Get the minimum value in a sequence."""

    class Help:
        synopsis = "get the minimum value in a sequence"

    src = Attribute("Source sequence", required=True, type="expression")
    key = Attribute("Key", type="function", required=False, default=None, missing=False)

    def logic(self, context):
        objects, dst, key = self.get_parameters(context, 'src', 'dst', 'key')
        if not objects:
            self.throw('min.empty', 'src is empty', diagnosis="Moya can't calculate the minimum of an empty sequence.")
        if key is None:
            result = min(objects)
        else:
            key_callable = key.get_scope_callable(context)
            result = min(key_callable(obj) for obj in objects)
        self.set_context(context, dst, result)


class FilterSeq(DataSetter):
    """Filter members of a collection which don't pass a condition."""

    class Help:
        synopsis = "filter values from a sequence"
        example = """
        <dict dst="crew">
            <dict let:name="john" let:species="human" />
            <dict let:name="rygel" let:species="hynerian" />
            <dict let:name="aeryn" let:species="peacekeeper" />
        </dict>
        <filter-seq src="items:crew dst="crew" test="species !- 'hyneria'"/>
        <!-- [{'name': 'john', 'species':'human'}, {'name':'aeryn', 'species':'peacemaker'}] -->

        """

    src = Attribute("Source", required=True, type="expression")
    dst = Attribute("Destination", required=False, type="reference", default=None)
    test = Attribute("Condition", required=True, type="function")

    def get_value(self, context):
        objects, dst, func = self.get_parameters(context, 'src', 'dst', 'test')
        predicate = func.get_scope_callable(context)
        return [item for item in objects if predicate(item)]


class Sort(DataSetter):
    """Sort a sequence"""

    class Help:
        synopsis = "sort a sequence"
        example = """
        <dict dst="crew">
            <dict let:name="John" let:species="human" />
            <dict let:name="Rygel" let:species="hynerian" />
            <dict let:name="Aeryn" let:species="peacekeeper" />
        </dict>
        <sort src="crew" dst="crew" key="lower:name" />
        """

    src = Attribute("Source sequence", required=True, type="expression")
    dst = Attribute("Destination", required=False, type="reference", default=None)
    key = Attribute("Key expression", required=True, type="function")
    reverse = Attribute("Reverse order?", type="boolean", required=False, default=False)

    def get_value(self, context):
        objects, dst, func, reverse = self.get_parameters(context, 'src', 'dst', 'key', 'reverse')
        get_key = func.get_scope_callable(context)
        return sorted(objects,
                      reverse=reverse,
                      key=get_key)


class Repeat(ContextElementBase):
    """Repeat a block a set number of times, or indefinitely. You can leave a repeat loop prematurely with the [tag]break[/tag] tag.

    [alert Note]Be careful not to create infinite loops with this tag[/alert]

    """

    class Help:
        synopsis = """repeat a block"""

        example = """
        <repeat times="5">
            <echo>Candyman</echo>
        </repeat>
        """

    times = Attribute("Number of times to repeat (default is infinite)", type="expression", default=None)

    class Meta:
        is_loop = True

    def logic(self, context):
        times = self.times(context)
        if times is not None:
            try:
                times = int(times)
            except:
                self.throw("bad-value.not-a-number", "'times' must be a number if given")
        if times is None:
            while 1:
                yield DeferNodeContents(self)
        else:
            count = max(0, times)
            while count:
                yield DeferNodeContents(self)
                count -= 1


class While(ContextElementBase):
    """Repeat a block of code while a condition is true, or a [tag]break[/tag] tag is reached.

    [alert Note]Be careful not to create an [i]infinite[/i] loop with this tag.[/alert]

    """

    class Help:
        synopsis = "repeat a block while a condition is true"
        example = """

        <let i="5"/>
        <while test="i gt 0">
            <echo>${i}</echo>
            <let i="i-1"/>
        </while>


        """

    class Meta:
        is_loop = True

    test = Attribute("Condition", required=True, type="expression")

    def logic(self, context, _defer=DeferNodeContents):
        test = self.test
        while test(context):
            yield _defer(self)


class Do(ContextElementBase):
    """Repeat a block of code until a condition becomes true, or a [tag]break[/tag] is reached.

    Note that, unlike [tag]while[/tag] this tag will execute the enclosed block at least once.

    If the [c]until[/c] attribute isn't given, the enclosed block will be executed just once.

    """

    class Help:
        synopsis = "repeat a block until a condition becomes true"
        example = """

        <let i="1"/>
        <do until="i==2">
            <echo>${i}</echo>
            <let i="i+1"/>
        </do>
        <!-- prints "1" -->

        """

    class Meta:
        is_loop = True

    until = Attribute("Condition", required=False, type="expression")

    def logic(self, context):
        if not self.has_parameter('until'):
            yield DeferNodeContents(self)
        else:
            test = self.test
            while 1:
                yield DeferNodeContents(self)
                if test(context):
                    break


class Break(ContextElementBase):
    """This tag will [i]break[/i] a loop such as [tag]while[/tag], [tag]for[/tag]. When Moya encounters this tag, it jumps to the statement after the loop."""

    class Help:
        synopsis = """end a loop prematurely"""
        example = """

        <let crew="['John', 'Rygel', 'Scorpius', 'Aeryn']"/>
        <for src="crew" dst="character">
            <if test="character == 'Scorpius'">
                <echo>Taking off before Scorpius gets on board!</eco>
                <break>
            </if>
            <echo>${character} is on board</echo>
        </for>

        """

    def logic(self, context):
        raise BreakLoop()


class Continue(ContextElementBase):
    """When Moya encounters this tag in a loop, such as [tag]while[/tag] or [tag]for[/tag], it ignores the remaining code in the block and [i]continues[/i] to the next item in the loop."""

    class Help:
        synopsis = """skip remaining code in a loop"""
        example = """

        <let crew="['John', 'Rygel', 'Scorpius', 'Aeryn']"/>
        <for src="crew" dst="character">
            <if test="character == 'Scorpius'">
                <echo>Scorpius is not allowed on board!</eco>
                <continue/>
            </if>
            <echo>${character} is on board</echo>
        </for>


        """

    def logic(self, context):
        raise ContinueLoop()


class Macro(ContextElementBase):
    """Defines a [link moyacode#macros]macro[/link]."""

    class Help:
        synopsis = """define a re-usable block of code"""
        example = """
        <macro docname="greet">
            <echo>Hello, ${name}!<echo>
        </macro>
        """

    def lib_finalize(self, context):
        for signature in self.children('signature'):
            self.validator = signature.validator
            self.validate_call = self.validator.validate


class Preflight(Macro):
    """A pre-flight check is used to detect potential problems, such as missing settings."""

    class Help:
        synopsis = """check initial settings"""


class ReturnDict(ContextElementBase):
    """
    Shortcut to return a dictionary. For example, the following macro returns a dictionary:

    [code xml]
    <macro docname="get_character">
        <return>
            <dict>
                <str dst="rygel">Hynerian</str>
                <str dst="john">Human</str>
            </dict>
        </return>
    </macro>
    [/code]

    We could shorten the above using the [tag]return-dict[/tag] as follows:

    [code xml]
    <macro docname="get_character">
        <return-dict>
            <str dst="rygel">Hynerian</str>
            <str dst="john">Human</str>
        </return-dict>
    </macro>
    [/code]

    """

    class Help:
        synopsis = "shortcut to return a dictionary"

    def logic(self, context):
        data = self.get_let_map(context).copy()
        context['_return'] = data
        with context.scope('_return'):
            yield DeferNodeContents(self)
        raise Unwind()


class ReturnScope(ContextElementBase):
    """
    Return values from the current scope.

    This tag is useful in macros, widgets, and other callable tags where you want to return a number of values in a dictionary.

    For example, the following will return a dictionary containing two keys:

    [code xml]
    <return-scope values="foo, bar"/>
    [/code]

    This is equivalent to the following:

    [code xml]
    <return value="{'foo': foo, 'bar': bar}"/>
    [/code]

    If you *don't* specify the [c]values[/c] attribute, Moya will read the values from the enclosed text (one key per line).
    The following code is equivalent to the above:

    [code xml]
    <return-scope>
        foo
        bar
    </return-scope>
    [/code]

    """

    values = Attribute("Values to return", type="commalist", required=False, default=None)
    default = Attribute("Default for missing values", type="expression", required=False, default=None)

    class Help:
        synopsis = "return values from the current scope"

    def logic(self, context):
        names, default = self.get_parameters(context, 'values', 'default')
        if names is None:
            names = [l.strip() for l in context.sub(self.text).splitlines() if not l.isspace()]
        get = context.get
        context['_return'] = {name: get(name, default) for name in names}
        raise Unwind()


class ReturnStr(ContextElementBase):
    """A shortcut to returning a string."""

    class Help:
        synopsis = "shortcut to return a string"
        example = """
        <macro docname="get_text">
            <return-str>Hello, World</return-str>
        </macro>
        """

    def logic(self, context):
        context['_return'] = context.sub(self.text)
        raise Unwind()


class ReturnFalse(ContextElementBase):
    """
    A shortcut to return False.

    The following two lines are equivalent:

    [code xml]
    <return-false/>
    <return value="no" />
    [/code]

    """

    class Help:
        synopsis = "shortcut to return false"

    def logic(self, context):
        context['_return'] = False
        raise Unwind


class ReturnTrue(ContextElementBase):
    """
    A shortcut to return True.

    The following two lines are equivalent:

    [code xml]
    <return-true/>
    <return value="yes" />
    [/code]

    """

    class Help:
        synopsis = "shortcut to return true"

    def logic(self, context):
        context['_return'] = True
        raise Unwind


class Return(ContextElementBase):
    """
    Used in a callable block such as a [tag]macro[/tag] or [tag]view[/tag] to return data.

    If you enclose any [i]data setter[/i] tag ([tag]int[/tag], [tag]str[/tag], [tag]list[/tag] etc.) in the return block, the result will be returned. For example, the following macro will return a list of three items:

    [code xml]
    <macro libname="get_crew">
        <return>
            <list>
                <str>John</str>
                <str>Scorpius</str>
                <str>Rygel</str>
            </list>
        </return>
    </macro>
    [/code]

    Alternatively, you may use the [c]value[/c] attribute to return the result of an expression. The following code is equivalent to the above:

    [code xml]
    <macro libname="get_crew">
        <return value="['John', 'Scorpius', 'Rygel']" />
    </macro>
    [/code]

    """

    class Help:
        synopsis = """return data from a macro or other callable"""

    value = Attribute("Value to return", type="expression", default=None)

    def logic(self, context):
        if self.has_parameter('value'):
            context['_return'] = ReturnContainer(value=self.value(context))
        else:
            context['_return'] = ReturnContainer()
            with context.scope('_return'):
                yield DeferNodeContents(self)
        raise Unwind()


class CacheReturn(ContextElementBase):
    """
    Return a value from a cache, if it exists. Otherwise, execute the enclosed block.

    This tag can be used to [i]memoize[/i] a [tag]macro[/tag] or other callable. Essentially, this means that if you call the macro a second time with the same parameters, it returns the previously calculated result. For macros that are slow to execute, this can result in significant speedups.

    For example, the following code calculates the [url http://en.wikipedia.org/wiki/Factorial]factorial[/url] of a number:


    [code xml]
    <moya xmlns="http://moyaproject.com"
        xmlns:let="http://moyaproject.com/let">

        <macro docname="fact">
            <signature>
                <argument name="n"/>
            </signature>
            <cache-return key="n">
                <echo>calculating ${n}!</echo>
                <let f="1"/>
                <while test="n">
                    <let f="f*n" n="n-1"/>
                </while>
                <return value="f"/>
            </cache-return>
        </macro>

        <macro docname="main">
            <call macro="fact" let:n="7" dst="result"/>
            <echo>${result}</echo>
            <call macro="fact" let:n="7" dst="result"/>
            <echo>${result}</echo>
            <call macro="fact" let:n="7" dst="result"/>
            <echo>${result}</echo>
        </macro>

    </moya>
    [/code]

    If you run the above code, you will get the following output:

    [code]
    $ moya run cachereturn.xml
    calculating 7!
    5040
    5040
    5040
    [/code]

    The first time the [c]fact[/c] macro is called, Moya displays "calculating 7!" in the terminal. The second and third time, the text is [i]not[/i] displayed because the result is retrieved from the cache -- without the need to execute the code within [tag]cache-return[/tag].


    """

    class Help:
        synopsis = "cache returned values"

    cache = Attribute("Cache name", required=False, default="runtime")
    _for = Attribute("Time to cache for", required=False, default=0, type="timespan")
    key = Attribute("Cache key", required=False)
    keydata = Attribute("Cache data", type="expression", required=False)
    local = Attribute('Should the value be cached for this tag only?', type="boolean", default=True)

    class Meta:
        is_call = True
        one_of = [('key', 'keydata')]

    def logic(self, context):
        (cache_name,
         cache_time,
         cache_key,
         cache_key_data,
         cache_local) = self.get_parameters(context,
                                            'cache',
                                            'for',
                                            'key',
                                            'keydata',
                                            'local')
        if cache_key is None:
            cache_key = make_cache_key(cache_key_data)
        if cache_local:
            cache_key = "{}--{}".format(self.libid, cache_key)

        cache = self.archive.get_cache(cache_name)
        cache_result = cache.get(cache_key, Ellipsis)
        if cache_result is Ellipsis:
            call = context.get('.call', {})
            yield DeferNodeContents(self)
            if '_return' in call:
                value = _return = call['_return']
                if hasattr(_return, 'get_return_value'):
                    value = _return.get_return_value()
            else:
                value = None
            cache.set(cache_key, value, time=int(cache_time))
            context['_return'] = ReturnContainer(value=value)
            raise Unwind()

        else:
            context['_return'] = ReturnContainer(value=cache_result)
            raise Unwind()


class Done(ContextElementBase):
    """Exists the current callable immediately with no return value. Note, this is not equivalent to [tag]return[/tag] which returns [c]None[/c]."""

    class Help:
        synopsis = """return from a macro or callable without any data"""

    def logic(self, context):
        raise Unwind()


class Input(DataSetter):
    """
    Get data from the console.

    [alert WARNING]This tag should only be used in an interactive context, such as a [tag]command[/tag] tag.[/alert]

    """

    class Help:
        synopsis = "ask the user for information in a command"
        example = """
        <input dst="name">What is your name?</input>

        """

    default = ''
    _default = Attribute("Value to use if response is empty", default="", map_to="default")
    password = Attribute("Use password input?", default=False, type="boolean")

    def logic(self, context):
        default = self.default(context)
        text = context.sub(self.text) or ''
        if default:
            text += " ({})".format(default)
        if text:
            text += ' '
        console = context.root['console']
        if self.password(context):
            response = getpass.getpass(text)
        else:
            try:
                if PY3:
                    response = input(text)
                else:
                    response = raw_input(text).decode(sys.stdin.encoding or locale.getpreferredencoding(True))
            except EOFError:
                self.throw('input.eof', 'User hit Ctrl+D')
        if not response:
            response = default
        self.set_context(context,
                         self.dst(context),
                         response)


class Ask(DataSetter):
    """
    Ask the user a yes / no question.

    [alert WARNING]This tag should only be used in an interactive context, such as a [tag]command[/tag] tag.[/alert]

    """

    class Help:
        synopsis = "ask a yes / no question"
        example = """
        <ask dst="take_off">Would you like to take off?</ask>
        <echo if="take_off">Taking off!</echo>
        """

    default = False

    def logic(self, context):
        try:
            response = raw_input("%s (Y/N) " % (self.text.strip() or ''))
        except EOFError:
            self.throw('ask.eof', 'User hit Ctrl+D')
        response_bool = response.strip().lower() in ('yes', 'y')
        self.set_context(context,
                         self.dst(context),
                         response_bool)


class _LazyCallable(object):
    def __init__(self, context, _callable, args, kwargs):
        self.context = weakref.ref(context)
        self.callable = _callable
        self.args = args
        self.kwargs = kwargs

    def __call__(self):
        context = self.context()
        try:
            with context.frame():
                if getattr(self.callable, '_require_context', False):
                    result = self.callable(context, *self.args, **self.kwargs)
                else:
                    result = self.callable(*self.args, **self.kwargs)
        except Exception as e:
            # TODO: better reporting of lazy error
            log.exception("lazy error %s", e)
            raise
        else:
            if hasattr(result, 'get_return_value'):
                result = result.get_return_value()
            return result


class Call(ContextElementBase):
    """Call a [link moyacode#macros]macro[/link]."""

    class Help:
        synopsis = "invoke a macro"
        example = '<call macro="moya.auth#login" />'

    class Meta:
        is_call = True

    macro = Attribute("Macro", required=True)
    dst = Attribute("Destination for return value", type="reference")
    lazy = Attribute("If True the result will be evaluated lazily (i.e. when next referenced)", type="boolean")
    _from = Attribute("Application", default=None, type="application")

    def logic(self, context):
        macro, dst, lazy, app = self.get_parameters(context, 'macro', 'dst', 'lazy', 'from')
        items_map = self.get_let_map(context)
        app = app or self.get_app(context, check=False)

        if self.has_children:
            call = self.push_funccall(context)
            call.update(items_map)
            try:
                yield DeferNodeContents(self)
            finally:
                self.pop_funccall(context)
            args, kwargs = call.get_call_params()
        else:
            call = {}
            args = []
            kwargs = items_map

        lazy_callable = None
        if lazy:
            if not dst:
                self.throw('call.missing-dst', "A value for 'dst' is required for lazy calls")
            macro_app, macro_element = self.get_element(macro, app)

            if hasattr(macro_element, 'validate_call'):
                macro_element.validate_call(context, macro_element, kwargs)

            element_callable = self.archive.get_callable_from_element(macro_element,
                                                                      app=macro_app or app)
            lazy_callable = _LazyCallable(context, element_callable, args, kwargs)
            context.set_lazy(dst, lazy_callable)

        else:
            macro_app, macro_element = self.get_element(macro, app)
            if macro_element._meta.app_first_arg:
                call = {'args': [macro_app] + args}
            else:
                call = {}
                if args:
                    call['args'] = args
            call.update(kwargs)

            if hasattr(macro_element, 'validate_call'):
                macro_element.validate_call(context, macro_element, call)

            self.push_call(context, call, app=macro_app)
            try:
                if hasattr(macro_element, 'run'):
                    for el in macro_element.run(context):
                        yield el
                else:
                    yield DeferNodeContents(macro_element)
            finally:
                call = self.pop_call(context)
            if '_return' in call:
                value = _return = call['_return']
                if hasattr(_return, 'get_return_value'):
                    value = _return.get_return_value()
            else:
                value = None
            if dst is None:
                getattr(context.obj, 'append', lambda a: None)(value)
            else:
                context[dst] = value


class CallElement(ContextElementBase):
    """
    Call a element object.

    This tag calls an element retrieved with tags such as [tag]get-element[/tag]. For a general purpose call tag, see [tag]call[/tag].

    """

    class Help:
        synopsis = "invoke a macro element"
        example = """
        <get-element name="sushifinder#macro.check_stock" dst="element" />
        <call-element element="element" dst="result"/>

        """

    class Meta:
        is_call = True

    element = Attribute("An element object", type="expression", required=True)
    dst = Attribute("Destination for return value", type="reference")

    def logic(self, context):
        macro, dst = self.get_parameters(context, 'element', 'dst')

        try:
            macro_element = macro.__moyaelement__()
            macro_app = macro.app
        except:
            self.throw('call-element.not_element',
                       'must be called with an element object')

        if self.has_children:
            call = self.push_funccall(context)
            try:
                yield DeferNodeContents(self)
            finally:
                self.pop_funccall(context)
            args, kwargs = call.get_call_params()
            call = {'args': args}
            call.update(kwargs)
            call.update(self.get_let_map(context))
        else:
            call = self.get_let_map(context)

        if hasattr(macro_element, 'validate_call'):
            macro_element.validate_call(context, macro_element, call)

        self.push_call(context, call, app=macro_app)
        try:
            yield DeferNodeContents(macro_element)
        finally:
            call = self.pop_call(context)
        if '_return' in call:
            value = _return = call['_return']
            if hasattr(_return, 'get_return_value'):
                value = _return.get_return_value()
        else:
            value = None
        if dst is None:
            getattr(context.obj, 'append', lambda a: None)(value)
        else:
            context[dst] = value


class Defer(ContextElementBase):
    """Defer to a given element, such as a [tag]macro[/tag]. [i]Deferring[/i] to a macro is similar to calling it, but no new [i]scope[/i] is created. This means that the macro has access to the same variables where defer was called."""

    class Help:
        synopsis = """jump to another element"""
        example = """
        <macro docname="board">
            <echo>${character} is on board</echo>
        </macro>

        <macro docname="main">
            <let crew="['John', 'Rygel', 'Scorpius']"/>
            <for src="crew" dst="character">
                <defer to="board"/>
            </for>
        </macro>

        """

    element = Attribute("Element", type="expression", required=False, default=None)
    _to = Attribute("Element reference", required=False, default=None, map_to="element_ref")
    _from = Attribute("Application", default=None, type="application")

    def logic(self, context):
        element, element_ref, app = self.get_parameters(context, 'element', 'element_ref', 'from')

        app = app or self.get_app(context)
        if element is not None:
            if not hasattr(element, '__moyaelement__'):
                self.throw("bad-value.not-an-element", "Can't defer to '{!r}' because it's not an element".format(element))
            element = element.__moyaelement__()
        elif element_ref is not None:
            app, element = self.get_element(element_ref, app)
        else:
            self.throw("bad-value.missing-element", "No value given for 'element' or 'element_ref'")
        if element._element_class != "logic":
            self.throw("defer.not-logic", "This element can not be deferred to")

        if element.has_children:
            with self.defer(context, app):
                yield DeferNodeContents(element)


class Scope(LogicElement):
    """Creates a new temporary [i]scope[/i] from an object."""

    class Help:
        synopsis = "create a temporary scope"
        example = """
        <dict dst="species">
            <let john="human"/>
            <let rygel="hynerian"/>
        </dict>
        <scope object="species">
            John is a ${john}, Rygel is a ${rygel}
        </scope>
        """

    object_ = Attribute("Object", type="expression", name="object", required=True)

    def logic(self, context):
        obj = self.object(context)
        with context.data_scope(obj):
            yield DeferNodeContents(self)
