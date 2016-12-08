from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from ..context import Context, Expression, FalseExpression, TrueExpression, DefaultExpression
from ..context.errors import SubstitutionError
from .. import interface
from ..markup import Markup
from .enginebase import TemplateEngine
from . import errors
from ..html import escape, spaceless
from ..errors import AppError, MarkupError
from ..render import render_object
from ..context.missing import is_missing
from ..urlmapper import RouteError
from ..application import Application
from ..compat import text_type, string_types, implements_to_string, with_metaclass, implements_bool
from ..tools import make_cache_key, nearest_word
from .. import tools
from ..compat import urlencode, PY2
from . import lorem
from ..traceframe import Frame as TraceFrame

from fs.path import join, dirname
import bleach

import re
from copy import deepcopy
from collections import defaultdict, namedtuple
from itertools import chain
from operator import truth
import contextlib
import json

import logging
log = logging.getLogger('moya.template')

TranslatableText = namedtuple("TranslatableText",
                              ["text",
                               "location",
                               "comment",
                               "plural",
                               "context"])


class MoyaTemplateEngine(TemplateEngine):
    name = "moya"

    def __init__(self, archive, fs, settings):
        super(MoyaTemplateEngine, self).__init__(archive, fs, settings)
        from .environment import Environment
        self.env = Environment(fs, archive)

    def __repr__(self):
        return "<moyatemplates>"

    def check(self, path):
        """Check if a template exists, allow exception to propagate"""
        self.env.check_template(path)

    def exists(self, path):
        """Check if a template exists"""
        try:
            self.env.check_template(path)
        except errors.MissingTemplateError:
            return False
        else:
            return True

    def render(self, paths, data, base_context=None, app=None, **tdata):

        if isinstance(paths, Template):
            return self.render_template(paths, data, base_context=base_context, **tdata)
        if isinstance(paths, string_types):
            paths = [paths]
        if not paths:
            raise ValueError("No template paths to render")
        template = None
        for path in paths:
            if not path:
                continue
            try:
                template = self.env.get_template(path)
            except errors.MissingTemplateError:
                continue
            else:
                break
        if template is None:
            raise errors.MissingTemplateError(paths[-1])

        return self.render_template(template,
                                    data,
                                    base_context=base_context,
                                    app=app,
                                    **tdata)

    def render_template(self, template, data, base_context=None, **tdata):
        if base_context is None:
            base_context = Context(name="base_context")

        data = data.copy()
        data.update(tdata)
        app = tdata.pop('app')
        return template.render(data,
                               context=base_context,
                               environment=self.env,
                               app=app)


class _TemplateStackFrame(interface.AttributeExposer):
    #__slots__ = ['app', 'data', 'stack', 'current_node']
    __moya_exposed_attributes__ = ['app', 'data']

    def __init__(self, app, data=None):
        self.app = app
        self.data = data or {}
        self.stack = []
        self.current_node = None


@implements_to_string
class _TemplateFrameContextManager(object):

    def __init__(self, template, context, data, app=None):
        self.template = template
        self.context = context
        self.data = data
        self.app = app

    def __enter__(self):
        stack_frame = self.template.push_frame(self.context,
                                               self.app,
                                               data=self.data)
        return stack_frame

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.template.pop_frame(self.context)

    def __str__(self):
        return self.index


class NodeMeta(type):
    registry = {}

    def __new__(cls, name, base, attrs):
        new_class = type.__new__(cls, name, base, attrs)
        if getattr(new_class, 'tag_name', ''):
            cls.registry[new_class.tag_name] = new_class

        return new_class


@implements_bool
@implements_to_string
class TagParser(object):
    """Parses the contents of a template tag"""

    re_string = re.compile('\"(.*?)\"')

    def __init__(self, node, text, node_index):
        self.node = node
        self.text = text
        self.node_index = node_index

    def __repr__(self):
        return 'TagParser(%r, %r)' % (self.node, self.text)

    def __str__(self):
        return self.text

    def __bool__(self):
        return truth(self.text.strip())

    def syntax_error(self, msg, diagnosis=None):
        raise errors.TagSyntaxError(msg,
                                    self.node,
                                    *self.node.location,
                                    diagnosis=diagnosis)

    def consume(self, count):
        self.text = self.text[count:]

    def get_expression(self):
        brackets = False
        if self.text.lstrip().startswith('('):
            self.text = self.text.split('(', 1)[1]
            brackets = True
        try:
            expression, text = Expression.scan(self.text)
        except Exception as e:
            self.syntax_error("expression error ({})".format(text_type(e)))
        if brackets:
            text = text.lstrip()
            if not text.startswith(')'):
                self.syntax_error('expected end parenthesis')
            text = text[1:]
        self.text = text
        if not expression:
            return None
        return Expression(expression)

    def get_word(self):
        text = self.text.strip()
        if text.startswith(("'", '"')):
            quote = text[0]
            try:
                word = text[:text.index(quote, 1) + 1]
            except ValueError:
                self.syntax_error('expected end quote')
            self.text = text[len(word) + 1:]
            word = word[1:-1]
        else:
            word, _, text = self.text.strip().partition(' ')
            self.text = text.strip()
        return word.strip() or None

    def expect_expression(self):
        expression = self.get_expression()
        if expression is None:
            self.syntax_error("unable to parse expression from '{}'".format(self.text))
        return expression

    def expect_expression_or_end(self):
        expression = self.get_expression()
        return expression

    def expect_word(self, *words):
        word = self.get_word()
        if word is None:
            words_list = ", ".join(w.upper() for w in words)
            self.syntax_error("expected %s" % (words_list or 'a word'))
        elif words and word not in words:
            words_list = ", ".join("'%s'" % w for w in words)
            self.syntax_error("expected %s, not '%s'" % (words_list, word))
        return word

    def expect_word_or_end(self, *words):
        word = self.get_word()
        if word is None:
            return word
        if word not in words:
            words_list = ",".join("'%s'" % w for w in words)
            self.syntax_error("expected %s or end of tag, not '%s'" % (words_list, word))
        return word

    def expect(self, flags, words):
        words = list(words)
        if flags is None:
            flags = []
        map = {}
        while 1:
            word = self.get_word()
            if word is None:
                break
            if word in flags:
                map[word] = TrueExpression()
                flags.remove(word)
                continue
            if word not in words:
                words_list = ", ".join("'%s'" % w for w in words)
                self.syntax_error("expected %s or end of tag, not '%s'" % (words_list, word))
            expression = self.expect_expression()
            map[word] = expression
            words.remove(word)
        return map

    def expect_word_expression_map(self, *words):
        words = list(words)
        map = {}
        while 1:
            word = self.get_word()
            if word is None:
                break
            if word not in words:
                words_list = ", ".join("'%s'" % w for w in words)
                self.syntax_error("expected %s or end of tag, not '%s'" % (words_list, word))
            expression = self.expect_expression()
            map[word] = expression
            words.remove(word)
        return map

    def expect_re(self, re_expect, pattern_description):
        match = re_expect.match(self.text)
        if match is None:
            self.syntax_error("expected '%s'" % pattern_description)
        self.consume(match.end())
        return match

    def expect_end(self):
        if self:
            self.syntax_error("unexpected text in tag: '%s'" % self.text.strip())

    def expect_text(self):
        if not self:
            self.syntax_error("expected text")
        return self.text.strip()


@implements_to_string
class NodeRenderError(Exception):
    def __init__(self, node, msg, original=None, diagnosis=None):
        self.node = node
        self.msg = msg
        self.original = original
        self.diagnosis = diagnosis

    def __str__(self):
        return self.msg


class NodeType(object):
    tag_name = ""
    is_clause = False
    auto_close = False
    invisible = False

    def __init__(self, template, name, extra, location, lib=None):
        self.template = template
        self.name = name
        self.extra = extra
        self.location = location
        self.lib = lib
        self.children = []

    @property
    def code(self):
        return getattr(self.template, 'source', None)

    def template_app(self, archive, default):
        if self.lib is None:
            return default
        try:
            return archive.find_app(self.lib)
        except:
            return default

    def __repr__(self):
        if self.extra:
            return '{%% %s %s %%}' % (self.name, self.extra)
        else:
            return '{%% %s %%}' % (self.name,)

    def process_token(self, token, text, token_text):
        return False

    def render_error(self, msg, original=None, diagnosis=None):
        raise NodeRenderError(self, msg, original=original, diagnosis=diagnosis)

    def syntax_error(self, msg, diagnosis=None):
        raise errors.TagSyntaxError(msg, self, *self.location, diagnosis=diagnosis)

    def on_create(self, environment, parser):
        pass

    def render(self, environment, context, template, text_escape):
        yield iter(self.children)

    def on_clause(self, clause):
        pass

    def add_child(self, child):
        self.children.append(child)

    def _combine_text_nodes(self, nodes, _string_types=string_types):
        """Combines consecutive text nodes in to a single text node"""
        if not nodes:
            return []
        nodes = nodes[:]
        out_nodes = [nodes.pop(0)]
        append = out_nodes.append
        for node in nodes:
            if isinstance(node, _string_types) and isinstance(out_nodes[-1], _string_types):
                out_nodes[-1] += node
            else:
                append(node)
        return out_nodes

    def _parse_tag_name(self, t):
        return t.strip().partition(' ')[0].replace('-', '')

    def finalize(self, environment, template):
        self.children = self._combine_text_nodes(self.children)

    def describe(self, level=0):
        tab = "  "
        indent = tab * level
        print(indent + "{%% %s %s %%}" % (self.name, self.extra))
        for child in self.children:
            if isinstance(child, string_types):
                print('%s%s' % (tab * (level + 1), child))
            else:
                child.describe(level + 1)
                print('%s%s' % (tab * (level + 1), "{% end %}"))

    def get_app(self, context):
        return context.get('._t.app', None)

    def render_contents(self, environment, context, template, text_escape):
        with template.block(context, self) as frame:
            contents = template._render_frame(frame, environment, context, text_escape)
        return contents


class Node(with_metaclass(NodeMeta, NodeType)):
    pass


class TextNode(Node):
    """A single line of text that requires substitution"""

    def __init__(self, template, name, extra, location, text):
        super(TextNode, self).__init__(template, name, extra, location)
        self.text = text

    def render(self, env, context, template, text_escape):
        return context.sub(self.text, text_escape)


class ConsoleNode(Node):
    tag_name = "console"
    auto_close = True

    def on_create(self, environment, parser):
        self.expression = parser.expect_expression()
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        obj = self.expression.eval(context)
        from .. import pilot
        pilot.console.obj(context, obj)
        return ''


class ConsoleRenderNode(Node):
    tag_name = "consolerender"
    auto_close = True

    def on_create(self, environment, parser):
        self.expression = parser.expect_expression()
        options_map = parser.expect_word_expression_map('width')
        self.width = options_map.get('width', DefaultExpression(100))
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        from ..console import Console
        obj = self.expression.eval(context)
        try:
            width = int(self.width.eval(context))
        except:
            self.render_error('width should be an integer')
        if width < 10:
            self.render_error('width is too small')
        console = Console(html=True, width=width)
        console.obj(context, obj)
        html = console.get_text()
        return html


class LoremNode(Node):
    tag_name = "lorem"
    auto_close = True

    def on_create(self, environment, parser):
        self.type = parser.expect_word('p', 'paragraphs', 's', 'sentences', 'w', 'words', 't', 'title')
        self.count = parser.expect_expression()
        offset_map = parser.expect_word_expression_map('offset')
        self.offset = offset_map.get('offset', DefaultExpression(0))
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        count = self.count.eval(context)
        offset = self.offset.eval(context)
        try:
            count = int(count)
        except:
            self.render_error('count should be an integer')

        try:
            offset = int(offset)
        except:
            self.render_error('offset should be an integer')

        if self.type in ('p', 'paragraphs'):
            return lorem.paragraphs(count, offset)
        elif self.type in('s', 'sentences'):
            return lorem.sentences(count, offset)
        elif self.type in ('w', 'words'):
            return lorem.words(count, offset)
        elif self.type in ('t', 'title'):
            return lorem.title(count, offset)


class InspectNode(Node):
    tag_name = "inspect"
    auto_close = True

    def on_create(self, environment, parser):
        self.expression = parser.expect_expression()
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        obj = self.expression.eval(context)
        from ..console import Console
        c = Console(nocolors=True, text=True, width=120)
        text = c.obj(context, obj).get_text()
        html = "<pre>\n{}</pre>".format(escape(text))
        return html


class EscapeNode(Node):
    """Escape enclosed text"""
    tag_name = "escape"

    # def on_create(self, environment, parser):
    #     self.text = []

    # def process_token(self, token_type, text, token_text):
    #     if token_type == "tag":
    #         if self._parse_tag_name(text) == "endescape":
    #         #if text.strip().split(' ', 1)[0] == "endescape":
    #             return False
    #     self.text.append(token_text)
    #     return True

    # def finalize(self, environment, template):
    #     self.text = ''.join(self.text)

    def render(self, environment, context, template, text_escape):
        return text_escape(self.render_contents(environment, context, template, text_escape))
        #return text_escape(text)


class _EscapeCodeWrap(Node):
    """Shim to escape all html from a node"""
    def __init__(self, node):
        self._node = node

    def __getattr__(self, k):
        return getattr(self._node, k)

    def render(self, environment, context, template, text_escape):
        for c in self._node.render(environment, context, template, text_escape):
            yield escape(c)


class CodeNode(Node):
    """render enclosed code as escaped code"""
    tag_name = "code"

    def render(self, environment, context, template, text_escape):
        yield iter(child if isinstance(child, text_type) else _EscapeCodeWrap(child)
                   for child in self.children)


class PremailerNode(Node):
    """Transform HTML to be suitable for email clients"""
    tag_name = "premailer"

    def render(self, environment, context, template, text_escape):
        html = self.render_contents(environment, context, template, text_escape)
        # premailer is slow to import, particularly on rpi
        # Do it at runtime to avoid delaying startup
        try:
            import premailer
        except ImportError:
            self.render_error("{% premailer %} requires 'premailer' Python module")
        base_url = context.get('.request.url', None)
        try:
            html = premailer.transform(html, base_url=base_url)
        except Exception as e:
            log.exception('premailer transform failed')
            self.render_error("failed to post-process html for email ({}), please see logs".format(text_type(e)))
        yield html


class RootNode(Node):
    tag_name = "root"


class BlockNode(Node):
    tag_name = "block"

    def on_create(self, environment, parser):
        self.block_name = parser.expect_word()
        self.block_type = parser.expect_word_or_end("replace", "append", "prepend") or "replace"
        parser.expect_end()
        self.template.add_block(self.block_name, self)

    def render(self, environment, context, template, text_escape):
        nodes = template.get_render_block(environment, self.block_name)
        #with template.block(context, self):
        #with template.block(context, self) as frame:
        yield chain.from_iterable(node.children for node in nodes)


class EmptyBlockNode(BlockNode):
    tag_name = "emptyblock"
    auto_close = True


class DefNode(Node):
    tag_name = "def"

    def on_create(self, environment, parser):
        self.def_name = parser.expect_word()
        parser.expect_end()
        self.template.data["defs"][self.def_name] = self

    def render(self, environment, context, template, text_escape):
        return ''


class CallNode(Node):
    tag_name = "call"
    auto_close = True

    def on_create(self, environment, parser):
        self.only = False
        self.name_expression = parser.expect_expression()
        self.with_expression = None
        words = ['with', 'only']
        while words:
            word = parser.expect_word_or_end(*words)
            if word is None:
                break
            words.remove(word)
            if word == "with":
                self.with_expression = parser.get_expression()
            elif word == "only":
                self.only = True
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        call_name = self.name_expression.eval(context)

        for data in reversed(self.template.get_extended_data(environment)):
            node = data['defs'].get(call_name, None)
            if node is not None:
                break

        if node is None:
            self.render_error("template function '%s' has not yet been defined" % call_name)
        if self.with_expression is not None:
            with_values = self.with_expression.eval(context)
            if not isinstance(with_values, (list, tuple)):
                with_values = [with_values]
            with_frame = {}

            for value in with_values:
                if hasattr(value, 'items'):
                    with_frame.update(value)
                else:
                    self.render_error("{% with %} takes a key/value pair or a mapping (not %r)" % value)

            if self.only:
                with template.frame(context, with_frame):
                    yield iter(node.children)
            else:
                scopes = context.set_new('._scopes', [])
                index = "._scopes.%i" % len(scopes)
                scopes.append(with_frame)
                try:
                    with context.scope(index):
                        yield iter(node.children)
                finally:
                    scopes.pop()
        else:
            if self.only:
                with template.block(context, self):
                    yield iter(node.children)
            else:
                yield iter(node.children)


class IfNode(Node):
    tag_name = "if"
    clauses = ["else", "elif"]

    def on_create(self, environment, parser):
        self.if_expression = parser.expect_expression()
        parser.expect_end()
        self.else_clause = False
        self.true_children = []
        self.else_children = []

    def on_clause(self, clause):
        if clause.name == "else":
            self.else_children.append((TrueExpression(), []))
        else:
            self.else_children.append((clause.condition, []))
        self.else_clause = True

    def add_child(self, child):
        if self.else_clause:
            self.else_children[-1][1].append(child)
        else:
            self.true_children.append(child)

    def finalize(self, environment, template):
        self.children = self._combine_text_nodes(self.children)
        self.else_children = self._combine_text_nodes(self.else_children)

    def render(self, environment, context, template, text_escape):
        if self.if_expression.eval(context):
            yield iter(self.true_children)
        else:
            for condition, children in self.else_children:
                if condition.eval(context):
                    yield iter(children)
                    break


class WithNode(Node):
    tag_name = "with"

    def on_create(self, environment, parser):
        self.with_expression = parser.expect_expression()
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        with_values = self.with_expression.eval(context)

        if not isinstance(with_values, (list, tuple)):
            with_values = [with_values]
        with_frame = {}
        for value in with_values:
            if hasattr(value, 'items'):
                for k, v in value.items():
                    with_frame[k] = v
            else:
                self.render_error("{{% with %}} takes a key/value pair or a mapping (not {})".format(context.to_expr(value)))

        scopes = context.set_new_call('._scopes', list)
        index = "._scopes.%i" % len(scopes)
        try:
            scopes.append(with_frame)
            with context.scope(index):
                yield iter(self.children)
        finally:
            scopes.pop()


class ElseNode(Node):
    tag_name = "else"
    is_clause = True

    def on_create(self, environment, parser):
        parser.expect_end()


class EmptyNode(Node):
    tag_name = "empty"
    is_clause = True

    def on_create(self, environment, parser):
        parser.expect_end()


class ElifNode(Node):
    tag_name = "elif"
    is_clause = True

    def on_create(self, environment, parser):
        self.condition = parser.expect_expression()
        parser.expect_end()


class _EmptySequence(object):
    """An always empty iterator"""
    def next(self):
        raise StopIteration


_last_value = object()


class ForNode(Node):
    tag_name = "for"
    clauses = ["empty"]
    _empty = _EmptySequence()

    _re_for = re.compile(r"^(.*?) in ")

    def on_clause(self, clause):
        if clause.name == "empty":
            self.empty_clause = True

    def add_child(self, child):
        if self.empty_clause:
            self.empty_children.append(child)
        else:
            self.children.append(child)

    def finalize(self, environment, template):
        self.children = self._combine_text_nodes(self.children)
        self.empty_children = self._combine_text_nodes(self.empty_children)

    def on_create(self, environment, parser):
        self.empty_clause = False
        self.empty_children = []
        match = parser.expect_re(self._re_for, "<items list> in")
        assign = match.groups()[0]
        self.sequence = parser.expect_expression()
        self.assign = [t.strip() for t in assign.split(',')]

        exp_map = parser.expect(["reverse"], ["if", "sort"])
        self.if_expression = exp_map.get('if', TrueExpression())
        self.sort_expression = exp_map.get('sort', None)
        self.reverse_expression = exp_map.get('reverse', FalseExpression())

    def render(self, environment, context, template, text_escape):
        sequence = self.sequence.eval(context)
        assign = self.assign
        children = self.children
        try:
            seq_iter = iter(sequence)
        except:
            seq_iter = self._empty

        if self.sort_expression is not None:
            reverse = bool(self.reverse_expression.eval(context))
            sort_function = self.sort_expression.make_function(context=context)
            seq_iter = iter(sorted((v for v in seq_iter),
                                   key=sort_function.get_scope_callable(context),
                                   reverse=reverse))

        if_eval = self.if_expression.eval

        for_stack = context.set_new('._for_stack', [])
        forloop = {'first': True, 'last': False}
        for_scope = {'forloop': forloop}
        for_stack.append(for_scope)

        context['._for'] = for_stack[-1]
        try:
            empty = True
            with context.scope('._for'):
                context_set = for_scope.__setitem__
                if len(assign) == 1:
                    assign = assign[0]
                    value = next(seq_iter, _last_value)
                    while value is not _last_value:
                        next_value = next(seq_iter, _last_value)
                        forloop['last'] = next_value is _last_value
                        context_set(assign, value)
                        if if_eval(context):
                            empty = False
                            yield iter(children)
                            forloop['first'] = False
                        value = next_value
                else:
                    value = next(seq_iter, _last_value)
                    while value is not _last_value:
                        next_value = next(seq_iter, _last_value)
                        forloop['last'] = next_value is _last_value
                        for name, subvalue in zip(assign, value):
                            context_set(name, subvalue)
                        if if_eval(context):
                            empty = False
                            yield iter(children)
                            forloop['first'] = False
                        value = next_value
            if empty and self.empty_children:
                yield iter(self.empty_children)

        except:
            self.render_error('unable to iterate over {}'.format(context.to_expr(sequence)))

        finally:
            for_stack.pop()
            if for_stack:
                context['._for'] = for_stack[-1]
            else:
                context.safe_delete('._for')


class EmitNode(Node):
    """Emit raw unescaped text """
    tag_name = "emit"
    auto_close = True

    def on_create(self, environment, parser):
        self.emit_text = parser.get_word()
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        yield self.emit_text


class ExtendsNode(Node):
    """Extends a base template"""
    tag_name = "extends"
    auto_close = True
    invisible = True

    def on_create(self, environment, parser):
        base_path = dirname(self.template.raw_path)
        path = parser.expect_word()
        word = parser.expect_word_or_end('from')
        lib = self.lib

        if word == 'from':
            app_lib = parser.expect_word()
            if environment.archive is not None:
                try:
                    path = environment.archive.resolve_template_path(path, app_lib, base_path=base_path)
                    lib = environment.archive.get_lib(app_lib)
                except AppError as e:
                    self.render_error(text_type(e))

        else:
            path = join(base_path, path)

        self.template.extend(environment, path, self, lib)
        parser.expect_end()


class RenderNode(Node):
    """Renders an object"""
    tag_name = "render"
    auto_close = True

    def on_create(self, environment, parser):
        self.unique = False
        self.target_expression = DefaultExpression("html")
        self.options_expression = DefaultExpression({})
        self.with_expression = DefaultExpression(None)
        self.render_expression = parser.expect_expression()
        while 1:
            word = parser.expect_word_or_end('to', 'set', 'with', 'unique')
            if word is None:
                break
            if word == 'to':
                self.target_expression = parser.expect_expression()
            elif word == 'set':
                self.options_expression = parser.expect_expression()
            elif word == 'with':
                self.with_expression = parser.expect_expression()
            elif word == 'unique':
                self.unique = True
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        render_obj = self.render_expression.eval(context)
        if is_missing(render_obj):
            return
        options = self.options_expression.eval(context)
        target = self.target_expression.eval(context)
        with_ = self.with_expression.eval(context)
        if with_ is not None:
            options['with'] = with_
        options['unique'] = self.unique
        try:
            yield render_object(render_obj,
                                environment.archive,
                                context,
                                target=target,
                                options=options)
        except errors.MissingTemplateError as e:
            self.render_error('Missing template: "%s"' % e.path, original=e)
        except errors.TagError as e:
            self.render_error(text_type(e), original=e)


class RenderAllNode(Node):
    tag_name = "renderall"
    auto_close = True

    def on_create(self, environment, parser):
        self.unique = False
        self.target_expression = DefaultExpression("html")
        self.options_expression = DefaultExpression({})
        self.render_expression = parser.expect_expression()
        self.with_expression = DefaultExpression({})
        while 1:
            word = parser.expect_word_or_end('to', 'set', "unique", "with")
            if word is None:
                break
            if word == 'to':
                self.target_expression = parser.expect_expression()
            elif word == 'set':
                self.options_expression = parser.expect_expression()
            elif word == "unique":
                self.unique = True
            elif word == "with":
                self.with_expression = parser.expect_expression()
        parser.expect_end()

    def get_renderables(self, context):
        render_sequence = self.render_expression.eval(context)
        return render_sequence

    def render(self, environment, context, template, text_escape, _as_dict=tools.as_dict, _render_object=render_object):
        options = _as_dict(self.options_expression.eval(context))
        render_sequence = self.get_renderables(context)
        if not render_sequence:
            return ''
        target = self.target_expression.eval(context)
        with_map = _as_dict(self.with_expression.eval(context))
        if with_map:
            options['with'] = with_map
        renders = [_render_object(render_obj,
                                  environment.archive,
                                  context,
                                  target=target,
                                  options=options) for render_obj in render_sequence]
        if self.unique:
            render_set = set()
            unique_renders = []
            for render in renders:
                if render not in render_set:
                    render_set.add(render)
                    unique_renders.append(render)
            renders = unique_renders

        return ''.join(renders)


class ChildrenNode(RenderAllNode):
    tag_name = "children"
    auto_close = True

    def on_create(self, environment, parser):
        self.unique = False
        self.target_expression = DefaultExpression("html")
        self.options_expression = DefaultExpression({})
        self.render_expression = Expression("self.children")
        self.with_expression = DefaultExpression({})
        while 1:
            word = parser.expect_word_or_end('to', 'set', "unique", "with")
            if word is None:
                break
            if word == 'to':
                self.target_expression = parser.expect_expression()
            elif word == 'set':
                self.options_expression = parser.expect_expression()
            elif word == "unique":
                self.unique = True
            elif word == "with":
                self.with_expression = parser.expect_expression()
        parser.expect_end()


class URLNode(Node):
    """Generates a URL from url mappers"""
    tag_name = "url"
    auto_close = True

    def on_create(self, environment, parser):
        self.url_name_expression = parser.expect_expression()
        expression_map = parser.expect_word_expression_map("with", "from", "query", 'base')
        self.params_expression = expression_map.get('with')
        self.in_expression = expression_map.get('from')
        self.qs_expression = expression_map.get('query')
        self.base_expression = expression_map.get('base')
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        url_name = self.url_name_expression.eval(context)
        qs = self.qs_expression.eval(context) if self.qs_expression else None
        base = self.base_expression.eval(context) if self.base_expression else None

        if is_missing(url_name):
            diagnosis_msg = "Did you mean to use a literal? i.e. {{% url \"{name}\" %}} rather than {{% url {name} %}}"
            diagnosis = diagnosis_msg.format(name=text_type(self.url_name_expression.exp))
            self.render_error("URL name is missing from context",
                              diagnosis=diagnosis)
        try:
            url_name = text_type(url_name)
        except:
            self.render_error("URL name must be a string, not %r" % url_name, self)

        if self.in_expression is not None:
            _in = self.in_expression.eval(context)
            if isinstance(_in, Application):
                app = _in
            else:
                try:
                    app = environment.archive.detect_app(context, _in)
                except Exception as e:
                    self.render_error(text_type(e),
                                      original=e,
                                      diagnosis="Check the 'from' attribute for typos.")
        else:
            app = self.template_app(environment.archive, context.get('._t.app', None))
            if app is None:
                diagnosis = '''You can specify the app with an 'from' clause, e.g {% url "post" from "blog" %}'''
                self.render_error("Could not detect app to get url",
                                  diagnosis=diagnosis)

        if self.params_expression is not None:
            params = self.params_expression.eval(context)
        else:
            params = {}

        for k, v in params.items():
            if is_missing(v):
                self.render_error("URL parameter '{}' must not be missing (it is {!r})".format(k, v),
                                  diagnosis="Moya is unable to generate a URL because one of the parameters refers to a value that is missing from the context.")

        try:
            url = context['.server'].get_url(app.name, url_name, params)
        except RouteError as e:
            self.render_error("Named URL '{}' not found in {} ({})".format(url_name, app, e),
                              diagnosis="Check the URL name for typos. Run 'moya urls' from the command line to see which url names are available.")
        else:
            if qs:
                if not hasattr(qs, 'items'):
                    self.render_error('Query requires a dict or other mapping object')
                try:
                    query_string = urlencode(qs)
                except:
                    self.render_error('Unable to encoded query {!r}'.format(qs),
                                      diagnosos="Convert the query object to a dictionary of strings")
                url = "{}?{}".format(url, query_string)
            if base:
                url = "{}{}".format(base, url)
            return url

        if not url:
            self.render_error("Named URL '{}' not found in {}".format(url_name, app),
                              diagnosis="Check the URL name for typos. Run 'moya urls' from the command line to see which url names are available.")

        return url


class MediaNode(Node):
    tag_name = "media"
    auto_close = True

    def on_create(self, environment, parser):
        self.path_expression = parser.expect_expression()
        expression_map = parser.expect_word_expression_map('media', 'from', 'index')
        self.media_expression = expression_map.get('media')
        self.in_expression = expression_map.get('from')
        self.index_expression = expression_map.get('index')
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        media = 'media'

        if not environment.archive.is_media_enabled:
            self.render_error("Media is not enabled",
                              diagnosis="check [media] section in settings")

        path = text_type(self.path_expression.eval(context))
        if self.index_expression is not None:
            media_url_index = self.index_expression.eval(context)
        else:
            media_url_index = None

        if path.startswith('/'):
            app = self.template_app(environment.archive, context.get('._t.app', None))
            media_path = environment.archive.get_media_url(context, None, media, path, url_index=media_url_index)
            return media_path

        if self.media_expression is not None:
            media = text_type(self.media_expression.eval(context))

        if self.in_expression is not None:
            _in = self.in_expression.eval(context)
            if isinstance(_in, Application):
                app = _in
            else:
                try:
                    app = environment.archive.find_app(_in)
                except Exception as e:
                    self.render_error(text_type(e))

        else:
            app = self.template_app(environment.archive, context.get('._t.app', None))
            if app is None:
                diagnosis = '''You can specify the app with an 'from' clause, e.g {{% media "post" from "blog" %}}'''
                self.render_error("Could not detect app to get media url",
                                  diagnosis=diagnosis)

        media_path = environment.archive.get_media_url(context, app, media, path, url_index=media_url_index)
        return media_path


class AttribNode(Node):
    """Renders a sequence of html attributes from a mapping expression"""
    tag_name = "attrib"
    auto_close = True
    _prefix = ""

    def on_create(self, environment, parser):
        self.attribs_expression = parser.expect_expression()
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        attribs = self.attribs_expression.eval(context)
        if not hasattr(attribs, 'items'):
            self.render_error('attribs tag requires a dictionary-like object (not {})'.format(context.to_expr(attribs)))
        attribs_text = []
        for k, v in attribs.items():
            if is_missing(v) or v is None:
                continue
            if isinstance(v, list):
                v = " ".join(text_type(item) for item in v if item)
            v = text_type(v)
            if v:
                attribs_text.append('{}="{}"'.format(escape(k), escape(v)))
        if not attribs_text:
            return ""
        if self._prefix:
            prefix = self._prefix
            return " " + " ".join(prefix + t for t in attribs_text)
        else:
            return " " + " ".join(attribs_text)


class DataAttribNode(AttribNode):
    """Renders a sequence of html data attributes from a mapping expression"""
    tag_name = "dataattrib"
    auto_close = True
    _prefix = "data-"


class URLEncodeNode(Node):
    """Renders a sequence of html attributes from a mapping expression"""
    tag_name = "urlencode"
    auto_close = True

    def on_create(self, environment, parser):
        self.attribs_expression = parser.expect_expression()
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        attribs = self.attribs_expression.eval(context)
        if not hasattr(attribs, 'items'):
            self.render_error('urlencode tag requires a dictionary like object (not {})'.format(context.to_expr(attribs)))
        encoded_url = urlencode(attribs)
        if PY2:
            encoded_url = encoded_url.decode('ascii')
        return encoded_url


class IncludeNode(Node):
    """Calls another template"""
    tag_name = "include"
    auto_close = True

    def on_create(self, environment, parser):
        self.path_expression = parser.expect_expression()
        expression_map = parser.expect_word_expression_map("from", "if")
        self.from_expression = expression_map.get('from', DefaultExpression(None))
        self.if_expression = expression_map.get('if', DefaultExpression(True))
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        if not self.if_expression.eval(context):
            return

        path = self.path_expression.eval(context)

        if isinstance(path, text_type):
            paths = [path]
        else:
            paths = path

        #app = self.from_expression.eval(context) or self.get_app(context)
        app = self.from_expression.eval(context) or self.template_app(environment.archive, context.get('._t.app', None))
        if app is None:
            self.render_error('unable to determine app')
        for i, _path in enumerate(paths, 1):
            if environment.archive is not None:
                path = environment.archive.resolve_template_path(_path, app)
            else:
                path = _path
            try:
                template = environment.get_template(path)
            except errors.MissingTemplateError as e:
                if i == len(paths):
                    self.render_error('unable to include missing template "{}"'.format(e.path), original=e)
            else:
                break

        with template.block(context, self) as frame:
            frame.stack.append(template.get_root_node(environment))
            yield template._render_frame(frame, environment, context, text_escape)


class InsertNode(Node):
    """Inserts code directly in to the template"""
    tag_name = "insert"
    auto_close = True

    def on_create(self, environment, parser):
        self.path_expression = parser.expect_expression()
        self.fs_expression = DefaultExpression('templates')
        self.escape = False
        while 1:
            word = parser.expect_word_or_end('fs', 'escape')
            if word is None:
                break
            if word == 'escape':
                self.escape = True
            elif word == 'fs':
                self.fs_expression = parser.expect_expression()

    def render(self, environment, context, template, text_escape):
        path = self.path_expression.eval(context)
        fs_name = text_type(self.fs_expression.eval(context))
        try:
            fs = environment.archive.get_filesystem(fs_name)
        except KeyError:
            self.render_error("no filesystem called '{}'".format(fs_name))
        content = fs.gettext(path)
        if self.escape:
            content = text_escape(content)
        return content


class SingleLineNode(Node):
    """Joins all lines in to a single line"""
    tag_name = "singleline"

    def render(self, environment, context, template, text_escape):
        text = self.render_contents(environment, context, template, text_escape)
        return ''.join(text.splitlines())


class CompactNode(Node):
    """Replace runs of whitespace with a single space"""
    tag_name = "compact"

    _re_whitespace = re.compile("\s+")

    def render(self, environment, context, template, text_escape):
        text = self.render_contents(environment, context, template, text_escape)
        _text = self._re_whitespace.sub(' ', text)
        return _text


class SpacelessNode(Node):
    """Remove whitespace between tags."""
    tag_name = "spaceless"

    def render(self, environment, context, template, text_escape):
        text = self.render_contents(environment, context, template, text_escape)
        return spaceless(text)


class VerbatimNode(Node):
    """Ignores all tags / substitution"""
    tag_name = "verbatim"

    def on_create(self, environment, parser):
        self.text = []

    def process_token(self, token_type, text, token_text):
        if token_type == "tag":
            if text.strip().split(' ', 1)[0] == "endverbatim":
                return False
        self.text.append(token_text)
        return True

    def finalize(self, environment, template):
        self.text = ''.join(self.text)

    def render(self, environment, context, template, text_escape):
        return self.text


class CacheNode(Node):
    tag_name = "cache"

    def on_create(self, environment, parser):
        self.node_index = parser.node_index
        words = ['for', 'key', 'in', 'if']
        self.for_expression = None
        self.key_expression = DefaultExpression('')
        self.in_expression = DefaultExpression('fragment')
        self.if_expression = DefaultExpression(True)
        while words:
            word = parser.expect_word_or_end(*words)
            if word is None:
                break
            words.remove(word)
            if word == "for":
                self.for_expression = parser.expect_expression()
            elif word == "key":
                self.key_expression = parser.expect_expression()
            elif word == "in":
                self.in_expression = parser.expect_expression()
            elif word == 'if':
                self.if_expression = parser.expect_expression()
        if self.for_expression is None:
            parser.syntax_error("FOR clause expected here")
        parser.expect_end()

    def render(self, environment, context, template, text_escape):

        if not self.if_expression.eval(context):
            # Don't cache
            return iter(self.children)

        key = make_cache_key(self.key_expression.eval(context))
        in_cache = text_type(self.in_expression.eval(context))
        cache_key = "{}.{}.{}".format(template.raw_path, self.node_index, key)
        cache = environment.get_cache(in_cache)
        cached_html = cache.get(cache_key, None)

        if isinstance(cached_html, text_type):
            return cached_html
        else:
            if cached_html is not None:
                # Appears to happen with memcache
                log.warning('cache returned non-unicode! %r', cached_html)

        html = self.render_contents(environment, context, template, text_escape)

        for_timespan = self.for_expression.eval(context)
        if for_timespan is None:
            for_ms = None
        else:
            try:
                for_ms = int(for_timespan) if for_timespan is not None else None
            except ValueError:
                self.render_error("FOR clause must be a number")

        cache.set(cache_key, html, time=for_ms)
        return html


class TransNode(Node):
    tag_name = "trans"

    def on_create(self, environment, parser):
        self.text = []
        self.plural_text = []
        self.plural_clause = False
        self.number_expression = None
        self.text_context = None
        words = ['comment', 'number', 'context']
        self.comment = None
        while 1:
            word = parser.expect_word_or_end(*words)
            if word is None:
                break
            if word == 'number':
                self.number_expression = parser.expect_expression()
            if word == 'comment':
                self.comment = parser.expect_word()
            if word == 'context':
                self.text_context = parser.expect_word()
            words.remove(word)

    def process_token(self, token_type, text, token_text):
        if token_type == "tag":
            #tag = text.strip().split(' ', 1)[0]
            tag = self._parse_tag_name(text)
            if tag in ("endtrans", "end"):
                return False
            else:
                if self.number_expression is None:
                    self.syntax_error("{% plural %} may only be used if the {% trans %} tag contains a 'number' attribute",
                                      diagnosis="For example; {% trans number post_count %}")
                if tag != 'plural':
                    self.render_error("{% trans %} tag may not contain other tags, except for {% plural %}")
                self.plural_clause = True
            return True
        if self.plural_clause:
            self.plural_text.append(token_text)
        else:
            self.text.append(token_text)
        return True

    def finalize(self, environment, template):
        text = self.text = ''.join(self.text).strip()
        if self.plural_clause:
            plural_text = self.plural_text = ''.join(self.plural_text).strip()
        else:
            plural_text = self.plural_text = None

        translatable_text = TranslatableText(text,
                                             self.location,
                                             self.comment,
                                             plural=plural_text,
                                             context=self.text_context)
        self.template.translatable_text.append(translatable_text)

    def render(self, environment, context, template, text_escape):
        app = self.template_app(environment.archive, context.get('._t.app', None))
        translations = environment.archive.get_translations(app, context.get('.languages', ['en']))
        if self.plural_clause:
            number = self.number_expression.eval(context)
            return context.sub(translations.ngettext(self.text, self.plural_text, number))
        else:
            return context.sub(translations.gettext(self.text))


class DataNode(Node):
    tag_name = "data"

    def on_create(self, environment, parser):
        self.text = []
        self.data_name = None
        word = parser.expect_word_or_end("as")
        if word == "as":
            self.data_name = parser.expect_word()
        parser.expect_end()

    def process_token(self, token_type, text, token_text):
        if token_type == "tag":
            if self._parse_tag_name(text) in ("enddata", "end"):
                return False
        self.text.append(token_text)
        return False

    def finalize(self, environment, template):
        self.text = ''.join(self.text)

    def render(self, environment, context, template, text_escape):
        try:
            data = self.data = json.loads(self.text)
        except Exception as e:
            self.render_error("data didn't validate as JSON ({})".format(e))
        if self.data_name is None and not isinstance(data, dict):
            self.render_error("data should be a JS object if no name is given")

        if self.data_name is None:
            context.update(self.data)
        else:
            context[self.data_name] = self.data
        return ''


class LetNode(Node):
    tag_name = "let"
    auto_close = True

    def on_create(self, environment, parser):
        self.let_expression = parser.expect_expression()
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        let = self.let_expression.eval(context)
        if not hasattr(let, 'items'):
            self.render_error("{{% let %}} expression must be a mapping type, e.g. foo='bar', not {}".format(context.to_expr(let)))
        try:
            context.update_base(let)
        except:
            self.render_error("{{% let %}} was unable to add {} to the template context".format(context.to_expr(let)))
        return ''


class MarkupNode(Node):
    tag_name = "markup"
    auto_close = True

    def on_create(self, environment, parser):
        self.markup_expression = parser.expect_expression()
        exp_map = parser.expect_word_expression_map('as', 'target', 'set')
        self.type_expression = exp_map.get('as', DefaultExpression("html"))
        self.target_expression = exp_map.get('target', DefaultExpression("html"))
        self.options_expression = exp_map.get('set', DefaultExpression({}))

        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        markup = text_type(self.markup_expression.eval(context) or '')
        target = self.target_expression.eval(context)
        markup_type = self.type_expression.eval(context)

        if isinstance(markup_type, list):
            for _markup_type in markup_type:
                if Markup.supports(_markup_type):
                    markup_type = _markup_type
                    break
            else:
                self.render_error("no supported markup in {}".format(tools.textual_list(markup_type)))

        options = self.options_expression.eval(context)

        if not Markup.supports(markup_type):
            self.render_error("markup '{}' is not supported".format(markup_type))

        try:
            markup_renderable = Markup(markup, markup_type)
            html = render_object(markup_renderable, environment.archive, context, target, options=options)
        except MarkupError as e:
            self.render_error("unable to render markup ({})".format(e))
        return html


class MarkupBlockNode(Node):
    tag_name = "markupblock"

    def on_create(self, environment, parser):
        exp_map = parser.expect_word_expression_map('as', 'target', 'set')
        self.type_expression = exp_map.get('as', DefaultExpression("html"))
        self.target_expression = exp_map.get('target', DefaultExpression("html"))
        self.options_expression = exp_map.get('set', DefaultExpression({}))
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        markup = self.render_contents(environment, context, template, text_escape)
        target = self.target_expression.eval(context)
        markup_type = self.type_expression.eval(context)
        options = self.options_expression.eval(context)

        if isinstance(markup_type, list):
            for _markup_type in markup_type:
                if Markup.supports(_markup_type):
                    markup_type = _markup_type
                    break
            else:
                self.render_error("no supported markup in {}".format(tools.textual_list(markup_type)))

        if not Markup.supports(markup_type):
            self.render_error("markup '{}' is not supported".format(markup_type))

        try:
            markup_renderable = Markup(markup, markup_type)
            html = render_object(markup_renderable, environment.archive, context, target, options=options)
        except MarkupError as e:
            self.render_error("unable to render markup ({})".format(e))
        except Exception as e:
            import traceback
            traceback.print_exc(e)
            self.render_error("{}".format(e))
        return html


class MarkdownNode(Node):
    tag_name = "markdown"

    def on_create(self, environment, parser):
        exp_map = parser.expect_word_expression_map('target', 'set')
        self.options_expression = exp_map.get('set', DefaultExpression({}))
        self.target_expression = exp_map.get('target', DefaultExpression("html"))
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        markup = self.render_contents(environment, context, template, text_escape)
        target = self.target_expression.eval(context)
        options = self.options_expression.eval(context)
        try:
            markup_renderable = Markup(markup, 'markdown')
            html = render_object(markup_renderable, environment.archive, context, target, options=options)
        except MarkupError as e:
            self.render_error("unable to render markup ({})".format(e))
        except Exception as e:
            import traceback
            traceback.print_exc(e)
            self.render_error("{}".format(e))
        return html


class ExtractNode(Node):
    tag_name = "extract"

    def on_create(self, environment, parser):
        exp_map = parser.expect_word_expression_map('as', 'replace', 'if')
        self.as_expression = exp_map.get('as', None)
        self.replace_expression = exp_map.get('replace', None)
        self.if_expression = exp_map.get('if', DefaultExpression(True))
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        markup = self.render_contents(environment, context, template, text_escape)
        replace_markup = ''
        extract_name = None
        if self.as_expression is not None:
            extract_name = self.as_expression.eval(context)
            if not isinstance(extract_name, text_type):
                self.render_error("name should be a string, not ({})".format(context.to_expr(extract_name)))
        if self.if_expression.eval(context):
            if extract_name is not None:
                context[extract_name] = markup
            if self.replace_expression is not None:
                filter_function = self.replace_expression.make_function(context)
                replace_markup = filter_function(context, contents=markup)
        else:
            replace_markup = markup
        return text_escape(replace_markup)


class SanitizeNode(Node):
    tag_name = "sanitize"

    _rules = {
        "tags":
        [
            'a',
            'abbr',
            'acronym',
            'b',
            'blockquote',
            'pre',
            'code',
            'em',
            'i',
            'li',
            'ol',
            'strong',
            'ul'
        ],
        "attributes":
        {
            'a': ['href', 'title'],
            'abbr': ['title'],
            'acronym': ['title']
        },
        "styles":
        [
        ],
        "strip": False,
        "strip_comments": True
    }

    def on_create(self, environment, parser):
        exp_map = parser.expect_word_expression_map('rules', 'tags', 'attributes', 'styles', 'strip', 'strip_comments', 'if')
        self.rules_expression = exp_map.get('rules', DefaultExpression(None))
        self.tags_expression = exp_map.get('tags', DefaultExpression(None))
        self.attributes_expression = exp_map.get('attributes', DefaultExpression(None))
        self.styles_expression = exp_map.get('styles', DefaultExpression(None))
        self.values_expression = exp_map.get('values', DefaultExpression(None))
        self.strip_expression = exp_map.get('strip', DefaultExpression(None))
        self.strip_comments_expression = exp_map.get('strip_comments', DefaultExpression(None))
        self.if_expression = exp_map.get('if', DefaultExpression(True))
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        markup = self.render_contents(environment, context, template, text_escape)

        if not self.if_expression.eval(context):
            return markup

        rules = self.rules_expression.eval(context)
        if rules is None:
            rules = self._rules
        rules = deepcopy(rules)

        tags = self.tags_expression.eval(context)
        attributes = self.attributes_expression.eval(context)
        styles = self.styles_expression.eval(context)
        values = self.styles_expression.eval(context)
        strip = self.strip_expression.eval(context)
        strip_comments = self.strip_comments_expression.eval(context)

        if tags is not None:
            rules['tags'] = tags
        if attributes is not None:
            rules['attributes'] = attributes
        if styles is not None:
            rules['styles'] = styles
        if strip is not None:
            rules['strip'] = bool(strip)
        if strip_comments is not None:
            rules['strip_comments'] = bool(strip_comments)
        if values is not None:
            rules['values'] = values

        def make_checker(tag, attributes, values):

            _attributes = attributes[:]
            _values = values

            def check_value(name, value):
                for attr in _attributes:
                    if name == attr:
                        if attr in _values:
                            if value not in _values[attr]:
                                return False
                        return True
                return False
            return check_value

        if "attributes" in rules and 'values' in rules:
            for tag, _attributes in list(rules["attributes"].items()):
                rules["attributes"][tag] = make_checker(tag, _attributes, rules['values'])

        if rules is None:
            clean_markup = bleach.clean(markup)
        else:
            if not isinstance(rules, dict):
                self.render_error("rules must be a mapping object, not {}".format(context.to_expr(rules)))
            try:
                clean_rules = {k: v for k, v in rules.items() if k in ['attributes', 'tags', 'styles', 'strip', 'strip_comments']}
                clean_markup = bleach.clean(markup, **clean_rules)
            except Exception as e:
                log.exception('{% sanitize %} template tag failed')
                self.render_error('failed to clean markup ({})'.format(e))

        return clean_markup


class SummarizeNode(Node):
    tag_name = "summarize"

    def on_create(self, environment, parser):
        exp_map = parser.expect_word_expression_map('chars')
        self.max_characters = exp_map.get('chars') or DefaultExpression(200)
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        markup = self.render_contents(environment, context, template, text_escape)

        target = "html"
        markup_type = "summary"
        markup_renderable = Markup(markup, markup_type)
        options = {"length": self.max_characters.eval(context)}

        html = render_object(markup_renderable, environment.archive, context, target, options=options)
        return html


TemplateExtend = namedtuple('TemplateExtend', ['path', 'node', 'lib'])


class NodeGenerator(object):
    #__slots__ = ['node', '_gen']

    def __init__(self, node, gen):
        self.node = node
        self._gen = gen

    def __repr__(self):
        return "<node-generator {!r} {!r}>".format(self.node, self._gen)

    @classmethod
    def create(cls, node, new_node, _isinstance=isinstance, _iter=iter):
        if _isinstance(new_node, (text_type, Node)):
            return new_node
        return cls(node, new_node)

    @classmethod
    def render(cls,
               node,
               environment,
               context,
               template,
               text_escape,
               _text_type=text_type,
               _isinstance=isinstance):
        gen = node.render(environment,
                          context,
                          template,
                          text_escape)
        if _isinstance(gen, _text_type):
            return gen
        return cls(node, gen)

    def __next__(self):
        return self._gen.__next__()

    def next(self):
        return self._gen.next()

    def __iter__(self):
        return self._gen.__iter__()

    def close(self):
        return self._gen.close()

    def throw(self, *args, **kwargs):
        return self._gen.throw(*args, **kwargs)

    def send(self, *args, **kwargs):
        return self._gen.send(*args, **kwargs)


class Template(object):

    re_special = re.compile(r'\{\%((?:\".*?\"|\'.*?\'|.|\s)*?)\%\}|(\{\#)|(\#\})')

    def __init__(self, source, path='?', raw_path=None, lib=None):
        self.source = source or ''
        self.source = self.source.replace('\t', '    ')
        self.path = path
        self.raw_path = path if raw_path is None else raw_path
        self.lib = lib

        self.parsed = False
        self.valid = False
        self.checked_extends = False
        self.root_node = None
        self._extend = TemplateExtend(None, None, None)
        self.blocks = {}
        self.render_blocks = {}
        self.data = defaultdict(dict)
        self.expressions = set()
        self._root_node = None
        self.translatable_text = []

    def __repr__(self):
        return "Template(path={!r})".format(self.path)

    def dump(self, environment):
        if self.parsed and not self.valid:
            return None
        self.parse(environment)
        state = self.__dict__.copy()

        def compile(exp):
            try:
                return Expression(exp).compile()
            except:
                return None
        state['compiled_expressions'] = filter(None, [compile(exp) for exp in self.expressions])
        return state

    @classmethod
    def load(cls, template_dump):
        state = template_dump
        Expression.insert_expressions(state.pop('compiled_expressions'))
        template = cls.new(state)
        return template

    @classmethod
    def new(cls, state):
        template = cls.__new__(cls)
        template.__dict__.update(state)
        return template

    def get_root_node(self, environment):
        template = self
        if environment is not None:
            while template._extend.path is not None:
                template = environment.get_template(template._extend.path)
        return template.root_node

    def extend(self, environment, path, node, lib):
        self._extend = TemplateExtend(path, node, lib)

    def check_extend(self, environment):
        """Check for recursive extends"""
        if self.checked_extends:
            return
        template = self
        path = self.raw_path
        visited = set()
        nodes = []
        self.checked_extends = True

        while 1:
            visited.add(path)
            if template._extend.path is not None:
                path, node, lib = template._extend
                template = environment.get_template(path, parse=False)
                nodes.append(node)
            else:
                break

            if path in visited:
                diagnosis = """A template may not be extended more than once in chain."""

                frames = []
                for node in reversed(nodes):
                    frame = TraceFrame(node.template.source,
                                       node.template.path,
                                       node.location[0],
                                       raw_location=node.template.raw_path,
                                       cols=node.location[1:],
                                       format='moyatemplate')
                    frames.append(frame)

                    raise errors.TemplateError("Recursive extends directive detected in '{}'".format(self.raw_path),
                                               node.template.path,
                                               node.location[0],
                                               diagnosis=diagnosis,
                                               trace_frames=frames)

    def get_extended_data(self, environment):
        extended_data = []
        template = self
        while 1:
            extended_data.append(template.data)
            if template._extend.path is not None:
                template = environment.get_template(template._extend.path)
            else:
                break
        return extended_data

    def add_block(self, block_name, node):
        self.blocks[block_name] = node

    def tokenize(self):
        find_special = self.re_special.finditer
        comment = 0
        lines = self.source.split('\n')
        last_line = len(lines) - 1
        tokens = []
        add_token = tokens.append

        def add_text(pos, token, text, remove_whitespace):
            if remove_whitespace:
                if not text.isspace():
                    text = text.lstrip()
                    remove_whitespace = False
                    add_token(("text", pos, text, text))
                    return False
                return True
            add_token(("text", pos, token, text))
            return False

        def pop_whitespace():
            while tokens:
                token_type, pos, token, text = tokens[-1]
                if token_type == 'text':
                    if text.isspace():
                        tokens.pop()
                        continue
                    else:
                        text = text.rstrip()
                        tokens.pop()
                        if text:
                            add_token((token_type, pos, text, text))
                        break
                break

        remove_whitespace = False
        for lineno, line in enumerate(self.source.splitlines()):
            if lineno != last_line:
                line += '\n'
            pos = 0
            for match in find_special(line):
                tag, begin_comment, end_comment = match.groups()
                start = match.start()
                end = match.end()
                token_text = match.group(0)

                if begin_comment:
                    if not comment and start > pos:
                        text = line[pos:start]
                        remove_whitespace = add_text((lineno, pos, start), text, text, remove_whitespace)
                    comment += 1
                    pos = end
                    continue
                if end_comment:
                    comment -= 1
                    if comment < 0:
                        raise errors.UnmatchedComment("Unbalanced end comment",
                                                      lineno + 1, start + 1, end,
                                                      diagnosis="Check that there is a corresponding {# for every #}")
                    pos = end
                    continue
                if comment:
                    continue

                if start > pos:
                    text = line[pos:start]
                    remove_whitespace = add_text((lineno, pos, start), text, text, remove_whitespace)

                if tag.startswith('-'):
                    tag = tag[1:]
                    pop_whitespace()
                if tag.endswith('-'):
                    tag = tag[:-1]
                    remove_whitespace = True

                add_token(("tag", (lineno, start, end), tag, token_text.replace('-', '')))

                pos = end
            if pos < len(line):
                if not comment:
                    text = line[pos:]
                    remove_whitespace = add_text((lineno, pos, len(line) - pos), text, text, remove_whitespace)
                pos = len(line)
        if comment:
            raise errors.UnmatchedComment("End of comment expected before end of template",
                                          lineno + 1, start + 1, len(line),
                                          diagnosis="Check that there is a corresponding {# for every #}")
        return tokens

    def parse(self, environment):
        try:
            root_node = self._parse(environment=environment)
        except errors.TokenizerError as e:
            frame = TraceFrame(self.source,
                               self.raw_path,
                               e.lineno,
                               cols=(e.start, e.end),
                               format='moyatemplate')
            raise errors.TemplateError(e.msg,
                                       self.path,
                                       e.lineno,
                                       diagnosis=e.diagnosis,
                                       trace_frames=[frame])
        except errors.NodeError as e:
            frame = TraceFrame(self.source,
                               self.raw_path,
                               e.lineno,
                               cols=(e.start, e.end),
                               format='moyatemplate')
            raise errors.TemplateError(e.msg,
                                       self.path,
                                       e.lineno,
                                       diagnosis=e.diagnosis,
                                       trace_frames=[frame])
        else:
            return root_node

    def _parse(self, environment=None):
        if environment is None:
            from .environment import Environment
            environment = Environment.make_default()
        if self.parsed:
            return self.root_node

        self.root_node = node = RootNode(self, 'root', '', (0, 0, 0))
        #self.parsed = True
        node_stack = [node]

        tokens = self.tokenize()
        for token_index, token in enumerate(tokens):
            token_type, (lineno, pos, endpos), text, token_text = token

            if node_stack[-1].process_token(token_type, text, token_text):
                continue
            if token_type == "text":
                if '${' in text:
                    self.expressions.update(Context.extract_expressions(text))
                    text_node = TextNode(self, "text", "",
                                         (lineno, pos, endpos + 1),
                                         text)
                    text_node.on_create(environment, TagParser(text_node, "", token_index))
                    node.add_child(text_node)
                else:
                    node.add_child(text)
            else:
                tag_name, _, extra = text.strip().partition(' ')
                tag_name = tag_name.replace('-', '')
                if tag_name.startswith("end"):
                    closing_tag = tag_name[3:].strip()
                    closed_tag = node_stack.pop()

                    if closed_tag.name == 'root':
                        raise errors.UnmatchedTag("End tag, {{% end{} %}}, has nothing to end".format(closing_tag),
                                                  node,
                                                  lineno + 1, pos + 1, endpos,
                                                  diagnosis="Check the syntax of the tag you are attempting to end (and that it exists).")

                    if closing_tag and closing_tag != closed_tag.name:
                        raise errors.UnmatchedTag("End tag, {{% end{} %}}, doesn't match {}".format(closing_tag, closed_tag),
                                                  node,
                                                  lineno + 1, pos + 1, endpos,
                                                  diagnosis="The {{% {close} %}} tag requires a corresponding {{% end-{close} %}}".format(close=closing_tag))
                    node.finalize(environment, self)
                    node = node_stack[-1]
                else:
                    new_node_class = NodeMeta.registry.get(tag_name)
                    if not new_node_class:
                        nearest = nearest_word(tag_name, NodeMeta.registry.keys())
                        if nearest is None:
                            diagnosis = "Check for typos."
                        else:
                            diagnosis = "Did you mean {{% {} %}} ?".format(nearest)
                        raise errors.UnknownTag("No such template tag, {{% {} %}}".format(tag_name),
                                                node,
                                                lineno + 1, pos + 1, endpos,
                                                diagnosis=diagnosis)
                    new_node = new_node_class(self,
                                              tag_name,
                                              extra,
                                              (lineno + 1, pos + 1, endpos),
                                              lib=self.lib)
                    new_node.on_create(environment, TagParser(new_node, extra, token_index))
                    if new_node.is_clause:
                        node.on_clause(new_node)
                    else:
                        if not new_node.invisible:
                            node.add_child(new_node)
                        if new_node.auto_close:
                            node.finalize(environment, self)
                        else:
                            node_stack.append(new_node)
                            node = new_node

        self.parsed = True
        self.valid = True
        return self.root_node

    def get_render_block(self, environment, block_name):
        chain = []
        template = self
        while 1:
            extend_node = template.blocks.get(block_name, None)
            if extend_node is not None:
                chain.append((extend_node.block_type, extend_node))
            if not template._extend.path:
                break
            template = environment.get_template(template._extend.path)

        if not chain:
            return []

        iter_chain = reversed(chain)
        block_type, node = next(iter_chain, None)
        nodes = [node]
        for block_type, block in iter_chain:
            if block_type == 'replace':
                nodes[:] = [block]
            elif block_type == "append":
                nodes.append(block)
            elif block_type == "prepend":
                nodes.insert(0, block)
        return nodes

    def get_block(self, environment, name):
        template = self
        while template is not None:
            if name in template.blocks:
                return template.blocks[name]
            if template._extend.path:
                template = environment.get_template(template._extend.path)
                continue
            break
        return None

    def push_frame(self, context, app, data=None):
        t_stack = context.set_new_call('._t_stack', list)
        stack_frame = _TemplateStackFrame(app, data=data)
        t_stack.append(stack_frame)
        context['._t'] = stack_frame
        context['.td'] = stack_frame.data
        context.push_frame('.td')
        return stack_frame

    def pop_frame(self, context):
        t_stack = context['._t_stack']
        t_stack.pop()
        try:
            last_stack = t_stack[-1]
            context['.td'] = last_stack.data
            context['._t'] = last_stack
        except IndexError:
            context.safe_delete('.td')
        context.pop_frame()

    def frame(self, context, data=None, app=None):
        if app is None:
            app = context.get('._t.app', None)
        return _TemplateFrameContextManager(self, context, data, app=app)

    @contextlib.contextmanager
    def block(self, context, node):
        t_stack = context.set_new_call('._t_stack', list)
        stack_frame = _TemplateStackFrame(node.get_app(context))
        stack_frame.stack.append(NodeGenerator.create(node, iter(node.children)))
        t_stack.append(stack_frame)
        yield stack_frame
        t_stack.pop()

    def _render_frame(self, frame, environment, context, sub_escape, _isinstance=isinstance, _next=next, _text_type=text_type, _Node=Node):
        output = []
        output_text = output.append

        node_render = NodeGenerator.render
        stack = frame.stack
        pop = stack.pop
        push = stack.append

        try:
            while stack:
                node = pop()
                if _isinstance(node, _text_type):
                    output_text(node)
                elif _isinstance(node, _Node):
                    frame.current_node = node
                    push(node_render(node, environment, context, self, sub_escape))
                else:
                    new_node = _next(node, None)
                    if new_node is not None:
                        push(node)
                        push(new_node)
            return ''.join(output)

        except errors.TemplateError:
            # Template errors should 'bubble up'
            raise

        except Exception as exc:
            self.on_error(context, frame.current_node, exc)

        finally:
            self._finalize_stack(stack)

    def on_error(self, context, current_node, exc):
        frames = []
        t_stack = context['._t_stack']
        base = context.get('.sys.base', '') or ''

        recent_node = current_node

        def relativefrom(base, path):
            if path.startswith(base):
                path = "./" + path[len(base):]
            return path

        last_node = None
        for i, frame in enumerate(t_stack):
            for _node in chain(frame.stack, [frame.current_node] if (i != len(t_stack) - 1) else []):
                node = _node.node if isinstance(_node, NodeGenerator) else _node
                if not isinstance(node, Node):
                    continue
                if node.tag_name != 'root' and node is not last_node:
                    frame = TraceFrame(node.template.source,
                                       node.template.path,
                                       node.location[0],
                                       raw_location=relativefrom(base, node.template.raw_path),
                                       cols=node.location[1:],
                                       format='moyatemplate')
                    frames.append(frame)
                last_node = node

        error_msg = text_type(exc)
        diagnosis = None

        if isinstance(exc, SubstitutionError):
            node = t_stack[-1].current_node
            lineno, start, end = node.location
            frame = TraceFrame(node.template.source,
                               node.template.path,
                               lineno + 1,
                               raw_location=relativefrom(base, node.template.raw_path),
                               cols=(start + exc.start + 1, start + exc.end),
                               format='moyatemplate')
            frames.append(frame)

        elif isinstance(exc, NodeRenderError):
            frame = TraceFrame(exc.node.template.source,
                               exc.node.template.path,
                               exc.node.location[0],
                               raw_location=relativefrom(base, exc.node.template.raw_path),
                               cols=exc.node.location[1:],
                               format='moyatemplate')
            frames.append(frame)
        else:
            if recent_node:
                frame = TraceFrame(recent_node.template.source,
                                   recent_node.template.path,
                                   recent_node.location[0],
                                   raw_location=relativefrom(base, recent_node.template.raw_path),
                                   cols=recent_node.location[1:],
                                   format='moyatemplate')
                frames.append(frame)

        if hasattr(exc, 'get_moya_frames'):
            frames.extend(exc.get_moya_frames())

        raise errors.TemplateError(error_msg,
                                   current_node.template.path,
                                   current_node.location[0],
                                   original=exc,
                                   diagnosis=diagnosis,
                                   trace_frames=frames)

    def _finalize_stack(self, stack):
        pop = stack.pop
        while stack:
            node = pop()
            try:
                node.close()
            except:
                pass

    @classmethod
    def _sub_escape(cls, text, _text_type=text_type, _hasattr=hasattr):
        if _hasattr(text, 'html_safe'):
            return _text_type(text)
        return _text_type('' if text is None else text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", "&#39;")

    def render(self, data=None, context=None, environment=None, app=None):
        if environment is None:
            from .environment import Environment
            environment = Environment.make_default()
        if context is None:
            context = Context()

        self.parse(environment)
        self.check_extend(environment)

        root = self.get_root_node(environment)
        with self.frame(context, data=data, app=app) as frame:
            frame.stack.append(root)
            return self._render_frame(frame, environment, context, self._sub_escape)


if __name__ == "__main__":

    test = """{% for n in 1..5 -%}
    ${n}
{%- endfor %}"""

    t = Template(test)

    for t in t.tokenize():
        print(repr(t[-1]))
