from __future__ import unicode_literals
from __future__ import print_function

import re

from ..context import Context, Expression, TrueExpression, DefaultExpression
from ..context.errors import SubstitutionError
from ..markup import Markup
from ..template.enginebase import TemplateEngine
from ..template.errors import MissingTemplateError, BadTemplateError
from ..html import escape, escape_quote
from ..template import errors
from ..errors import AppError
from ..render import render_object
from ..context.missing import is_missing
from ..urlmapper import RouteError
from ..application import Application
from ..compat import text_type, string_types, implements_to_string, with_metaclass, implements_bool
from ..tools import make_cache_key, nearest_word
from .. import tools
from ..compat import urlencode

from fs.path import pathjoin, dirname

from collections import defaultdict, namedtuple
from itertools import chain
from operator import truth
import json

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
        except MissingTemplateError:
            return False
        else:
            return True

    def render(self, paths, data, base_context=None, app=None, **tdata):

        if paths is None:
            paths = []
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
            except BadTemplateError:
                raise
            except MissingTemplateError:
                continue
            else:
                break
        if template is None:
            raise MissingTemplateError(paths[-1])

        return self.render_template(template, data, base_context=base_context, app=app, **tdata)

    def render_template(self, template, data, base_context=None, **tdata):
        if base_context is None:
            base_context = Context()

        if '_t' in base_context:
            tdata = base_context['_t'].copy().update(tdata)

        #save_app = base_context.root.get('app', None)
        #base_context.set_dynamic('.app', lambda context: context['._t.app'])
        #try:
        with base_context.root_stack('_t', tdata):
            with template.frame(base_context, data):
                try:
                    return template.render(base_context, self.env)
                except Exception as e:
                    if not hasattr(e, 'template_stack'):
                        e.template_stack = base_context['.__t_stack'][:]
                    raise
        #finally:
        #    base_context.root['app'] = save_app


@implements_to_string
class _TemplateFrame(object):

    def __init__(self, template, context, data):
        self.template = template
        self.context = context
        self.data = data

    def __enter__(self):
        self.template.push_frame(self.context, self.data)

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

    def syntax_error(self, msg):
        raise errors.TagSyntaxError(msg,
                                    self.node.template.path,
                                    *self.node.location,
                                    raw_path=self.node.template.raw_path,
                                    code=self.node.code)

    def consume(self, count):
        self.text = self.text[count:]

    def get_expression(self):
        brackets = False
        if self.text.lstrip().startswith('('):
            self.text = self.text.split('(', 1)[1]
            brackets = True
        expression, text = Expression.scan(self.text)
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

    def expect_word(self, *words):
        word = self.get_word()
        if word is None:
            words_list = " or ".join(w.upper() for w in words)
            self.syntax_error("expected %s" % (words_list))
        elif words and word not in words:
            words_list = " or ".join("'%s'" % w for w in words)
            self.syntax_error("expected %s, not '%s'" % (words_list, word))
        return word

    def expect_word_or_end(self, *words):
        word = self.get_word()
        if word is None:
            return word
        if word not in words:
            words_list = " or ".join("'%s'" % w for w in words)
            self.syntax_error("expected %s or end of tag, not '%s'" % (words_list, word))
        return word

    def expect_word_expression_map(self, *words):
        words = list(words)
        map = {}
        while 1:
            word = self.get_word()
            if word is None:
                break
            if word not in words:
                words_list = " or ".join("'%s'" % w for w in words)
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
            self.syntax_error("unexpected text in tag: %s" % self.text.strip())

    def expect_text(self):
        if not self:
            self.syntax_error("expected text")
        return self.text.strip()


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

    # @property
    # def template_lib(self):
    #     return self.template.raw_path.lstrip('/').split('/', 1)[0]

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
        raise errors.RenderError(msg,
                                 self.template.path,
                                 *self.location,
                                 raw_path=self.template.raw_path,
                                 code=self.code,
                                 original=original,
                                 diagnosis=diagnosis)

    def on_create(self, environment, parser):
        pass

    def render(self, environment, context, template, text_escape):
        yield iter(self.children)

    def on_clause(self, clause):
        pass

    def add_child(self, child):
        self.children.append(child)

    def _combine_text_nodes(self, nodes):
        """Combines consecutive text nodes in to a single text node"""
        if not nodes:
            return []
        nodes = nodes[:]
        out_nodes = [nodes.pop(0)]
        for node in nodes:
            if isinstance(node, string_types) and isinstance(out_nodes[-1], string_types):
                out_nodes[-1] += node
            else:
                out_nodes.append(node)
        return out_nodes

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
            self.render_error("Template function '%s' has not yet been defined" % call_name)
        if self.with_expression is not None:
            with_values = self.with_expression.eval(context)
            if not isinstance(with_values, (list, tuple)):
                with_values = [with_values]
            with_frame = {}

            for value in with_values:
                if hasattr(value, 'items'):
                    with_frame.update(value)
                else:
                    self.render_error("with takes a key/value pair or a mapping (not %r)" % value)

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
                with template.frame(context):
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
                self.render_error("with takes a key/value pair or a mapping (not %r)" % value)

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
        word = parser.expect_word_or_end('if')
        if word is not None:
            self.if_expression = parser.expect_expression()
        else:
            self.if_expression = TrueExpression(True)

    def render(self, environment, context, template, text_escape):
        sequence = self.sequence.eval(context)
        assign = self.assign
        children = self.children
        try:
            seq_iter = iter(sequence)
        except:
            seq_iter = self._empty
        if_eval = self.if_expression.eval

        for_stack = context.set_new('._for_stack', [])

        forloop = {'first': True,
                   'last': False}
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
            path = pathjoin(base_path, path)

        try:
            environment.get_template(path)
        except MissingTemplateError as e:
            self.render_error(text_type(e))
        self.template.extend(path, self, lib)
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
            return ''
        options = self.options_expression.eval(context)
        target = self.target_expression.eval(context)
        with_ = self.with_expression.eval(context)
        if with_ is not None:
            options['with'] = with_
        options['unique'] = self.unique
        try:
            return render_object(render_obj,
                                 environment.archive,
                                 context,
                                 target=target,
                                 options=options)
        except MissingTemplateError as e:
            self.render_error('Missing template: "%s"' % e.path)


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
                    app = environment.archive.find_app(_in)
                except Exception as e:
                    raise self.render_error(text_type(e), original=e, diagnosis="Check the 'from' attribute for typos.")
        else:
            app = self.template_app(environment.archive, context.get('._t.app', None))
            if app is None:
                diagnosis = '''You can specify the app with an 'from' clause, e.g {{% url "post" from "blog" %}}'''
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
        expression_map = parser.expect_word_expression_map('media', 'from')
        self.media_expression = expression_map.get('media')
        self.in_expression = expression_map.get('from')
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        media = 'media'

        path = text_type(self.path_expression.eval(context))

        if path.startswith('/'):
            app = self.template_app(environment.archive, context.get('._t.app', None))
            media_path = environment.archive.get_media_url(None, media, path)
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
                raise self.render_error("Could not detect app to get media url",
                                        diagnosis=diagnosis)

        media_path = environment.archive.get_media_url(app, media, path)
        return media_path


class AttribNode(Node):
    """Renders a sequence of html attributes from a mapping expression"""
    tag_name = "attrib"
    auto_close = True

    def on_create(self, environment, parser):
        self.attribs_expression = parser.expect_expression()
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        attribs = self.attribs_expression.eval(context)
        if not hasattr(attribs, 'items'):
            self.render_error('attribs tag requires a mapping')
        attribs_text = []
        for k, v in attribs.items():
            if is_missing(v) or v is None:
                continue
            if isinstance(v, list):
                v = " ".join(item for item in v if item)
            attribs_text.append('{}="{}"'.format(escape(k), escape_quote(v)))
        if not attribs_text:
            return ""
        return " " + " ".join(attribs_text)


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
            self.render_error('urlencode tag requires a mapping')
        encoded_url = urlencode(attribs).decode('ascii')
        return encoded_url


class IncludeNode(Node):
    """Calls another template"""
    tag_name = "include"
    auto_close = True

    def on_create(self, environment, parser):
        self.path_expression = parser.expect_expression()
        expression_map = parser.expect_word_expression_map("from")
        self.from_expression = expression_map.get('from', DefaultExpression(None))
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        path = self.path_expression.eval(context)
        app = self.from_expression.eval(context) or self.get_app(context)
        if environment.archive is not None:
            path = environment.archive.resolve_template_path(path, app)
        template = environment.get_template(path)
        return template.render(context, environment)


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
        content = fs.getcontents(path, 'rt')
        if self.escape:
            content = text_escape(content)
        return content


class SingleLineNode(Node):
    """Joins all lines in to a single line"""
    tag_name = "singleline"

    def render(self, environment, context, template, text_escape):
        text = template.render_nodes(self.children, environment, context, text_escape)
        return ''.join(text.splitlines())


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

        if cached_html is not None:
            return cached_html

        html = template.render_nodes(self.children,
                                     environment,
                                     context,
                                     text_escape)

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
            tag = text.strip().split(' ', 1)[0]
            if tag in ("endtrans", "end"):
                return False
            else:
                if self.number_expression is None:
                    raise errors.TagError("{% plural %} may only be used if the {% trans %} tag contains a 'number' attribute", self)
                if tag != 'plural':
                    raise errors.TagError("{% trans %} tag may not contain other tags, except for {% plural %}", self)
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
            if text.strip().split(' ', 1)[0] in ("enddata", "end"):
                return False
        self.text.append(token_text)
        return False

    def finalize(self, environment, template):
        self.text = ''.join(self.text)

    def render(self, environment, context, template, text_escape):
        try:
            data = self.data = json.loads(self.text)
        except Exception as e:
            raise errors.TagError("data didn't validate as JSON ({})".format(e), self)
        if self.data_name is None and not isinstance(data, dict):
            raise errors.TagError("data should be a JS object if no name is given", self)

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
            raise errors.TagError("{{% let %}} expression must be a mapping type, e.g. foo='bar', not {!r}".format(let), self)
        try:
            context.update(let)
        except:
            raise errors.TagError("{{% let %}} expression must be a mapping type, e.g. foo='bar', not {!r}".format(let), self)
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
        markup = text_type(self.markup_expression.eval(context))
        target = self.target_expression.eval(context)
        markup_type = self.type_expression.eval(context)
        markup_renderable = Markup(markup, markup_type)
        options = self.options_expression.eval(context)

        html = render_object(markup_renderable, environment.archive, context, target, options=options)
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
        markup = template.render_nodes(self.children, environment, context, text_escape)

        target = self.target_expression.eval(context)
        markup_type = self.type_expression.eval(context)
        markup_renderable = Markup(markup, markup_type)
        options = self.options_expression.eval(context)
        html = render_object(markup_renderable, environment.archive, context, target, options=options)
        return html


class SummarizeNode(Node):
    tag_name = "summarize"

    def on_create(self, environment, parser):
        exp_map = parser.expect_word_expression_map('chars')
        self.max_characters = exp_map.get('chars')
        parser.expect_end()

    def render(self, environment, context, template, text_escape):
        markup = template.render_nodes(self.children, environment, context, text_escape)

        target = "html"
        markup_type = "summary"
        markup_renderable = Markup(markup, markup_type)
        options = {"length": self.max_characters.eval(context)}

        html = render_object(markup_renderable, environment.archive, context, target, options=options)
        return html


TemplateExtend = namedtuple('TemplateExtend', ['path', 'node', 'lib'])


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

    def extend(self, path, node, lib):
        self._extend = TemplateExtend(path, node, lib)

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
                    add_token(("text", (lineno, pos, start), text, text))
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
                            tokens.append((token_type, pos, text, text))
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
                        raise errors.UnmatchedCommentError("Unbalanced end comment",
                                                           self.path,
                                                           lineno, start, end)
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

                add_token(("tag", (lineno, start, end), tag, token_text))

                pos = end
            if pos < len(line):
                if not comment:
                    text = line[pos:]
                    remove_whitespace = add_text((lineno, pos, len(line) - pos), text, text, remove_whitespace)
                pos = len(line)
        if comment:
            raise errors.UnmatchedCommentError("End of comment expected before end of template",
                                               self.path,
                                               lineno,
                                               start,
                                               end,
                                               code=self.template.source)
        return tokens

    def parse(self, environment):
        if self.parsed:
            return self.root_node
        self.root_node = node = RootNode(self, 'root', '', (0, 0, 0))
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
                if tag_name.startswith("end"):
                    closing_tag = tag_name[3:].strip()
                    closed_tag = node_stack.pop()
                    if closing_tag and closing_tag != closed_tag.name:
                        raise errors.UnmatchedTagError("End tag, '%s', doesn't match %r" % (closing_tag, closed_tag),
                                                       node.template.path,
                                                       lineno + 1,
                                                       pos + 1,
                                                       endpos,
                                                       raw_path=node.template.raw_path,
                                                       code=node.template.source)
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
                        raise errors.UnknownTagError("No such tag, {{% {} %}}".format(tag_name),
                                                     node.template.path,
                                                     lineno + 1,
                                                     pos + 1,
                                                     endpos,
                                                     raw_path=node.template.raw_path,
                                                     code=node.template.source,
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

        visited = {self.raw_path}
        template = self

        while template._extend.path:
            template = environment.get_template(template._extend.path)
            if template.raw_path in visited:
                raise errors.RecursiveExtendsError("Recursive extends directive detected (in '{}')".format(template.raw_path),
                                                   self.path,
                                                   *self.extend_node.location,
                                                   raw_path=self.raw_path,
                                                   code=self.extend_node.code)
            visited.add(template.raw_path)

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

    def get_top_block(self, environment, block_name):
        template = self
        top_block = None
        while 1:
            top_block = template.blocks.get(block_name, None)
            if top_block is not None:
                return top_block
            if template.extend_template_path:
                template = environment.get_template(template.extend_template_path)
            else:
                break
        return top_block

    def push_frame(self, context, data=None):
        """Pushes a new template frame"""
        if data is None:
            data = {}
        td = context.set_new('._td', [])
        td.append(data)
        context['.td'] = data
        context.push_frame('.td')
        return data

    def pop_frame(self, context):
        context['._td'].pop()
        try:
            context['.td'] = context['_td'][-1]
        except:
            context.safe_delete('.td')
        context.pop_frame()

    def frame(self, context, data=None):
        return _TemplateFrame(self, context, data)

    def render_nodes(self, nodes, environment, context, sub_escape):
        stack = nodes[::-1]
        return self._render_nodes(stack, environment, context, sub_escape)

    def _render_nodes(self, stack, environment, context, sub_escape):
        output = []
        output_text = output.append
        pop = stack.pop
        push = stack.append
        current_node = None

        try:
            while stack:
                node = pop()
                if isinstance(node, text_type):
                    output_text(node)
                elif isinstance(node, Node):
                    current_node = node
                    push(node.render(environment, context, self, sub_escape))
                else:
                    new_node = next(node, None)
                    if new_node is not None:
                        push(node)
                        push(new_node)
            return ''.join(output)
        except (errors.TagError, errors.TemplateError) as e:
            raise
        except SubstitutionError as e:
            lineno, start, end = current_node.location
            raise errors.RenderError(text_type(e),
                                     current_node.template.path,
                                     lineno + 1,
                                     start + e.start + 1,
                                     start + e.end,
                                     raw_path=current_node.template.raw_path,
                                     original=e.original,
                                     code=current_node.template.source)
        except Exception as e:
            raise errors.RenderError("render error",
                                     current_node.template.path,
                                     *current_node.location,
                                     raw_path=current_node.template.raw_path,
                                     original=e,
                                     code=current_node.template.source)

    def render(self, context, environment=None):
        self.parse(environment)
        stack = [self.get_root_node(environment)]

        def sub_escape(text):
            if hasattr(text, 'html_safe'):
                return text_type(text)
            return text_type('' if text is None else text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        return self._render_nodes(stack, environment, context, sub_escape)


if __name__ == "__main__":

    test = """{% for n in 1..5 -%}
    ${n}
{%- endfor %}"""

    t = Template(test)

    for t in t.tokenize():
        print(repr(t[-1]))
