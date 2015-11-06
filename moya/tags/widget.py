from __future__ import unicode_literals
from __future__ import print_function

from ..elements.registry import Meta
from ..elements import attributetypes
from ..elements.elementbase import ElementBase, Attribute, LogicElement
from ..logic import DeferNodeContents
from ..tools import textual_list, nearest_word
from ..context.missing import is_missing
from ..context.tools import to_expression
from ..compat import text_type, py2bytes
from .. import errors
from .. import namespaces

from collections import OrderedDict


class WidgetBase(LogicElement):
    _container = False

    class Meta:
        text_nodes = "text"
        is_call = True

    class NoTextMeta:
        text_nodes = None
        is_call = True

    def __init__(self, *args, **kwargs):
        self.init_args = (args, kwargs)
        super(WidgetBase, self).__init__(*args, **kwargs)

    def get_widget_app(self, context):
        app = None
        if self.has_parameter('from'):
            app = self.get_parameter(context, 'from') or None
        if app is None:
            try:
                app = self.archive.detect_app(context, self._lib_long_name)
            except:
                app = None
        if app is None:
            self.throw("widget.ambiguous-app",
                       "unable to detect app for this widget (you may need to supply the 'from' attribute)")
        return app

    def logic(self, context):
        widget_frame = context.current_frame
        content = context['.content']
        if is_missing(content):
            self.throw('widget.content-missing',
                       "widgets must be called in a content definition")

        td = self.get_all_parameters(context)
        td.pop('_if', None)
        _cachekey, _cachefor = self._cache
        cachekey, cachefor = None, None

        let_map = self.get_let_map(context)
        widget_app = self.get_widget_app(context)

        if _cachekey and _cachefor:
            with context.data_frame(td):
                cachekey = _cachekey(context)
                cachefor = _cachefor(context).milliseconds

            cachekey = "__widget__.{}.{}".format(self.libid, cachekey)
            cache = self.archive.get_cache('fragment')
            html = cache.get(cachekey, None)
            if html is not None:
                content.add_markup(self._tag_name, html)
                return

        if '_caller' not in td:
            td['_caller'] = self.get_proxy(context, context['.app'])

        def on_yield(context, app, content, element, data):
            context.push_frame(widget_frame)
            try:
                with self.defer(context, app=app):
                    with context.data_scope(data):
                        with content.node():
                            yield DeferNodeContents(element)
            finally:
                context.pop_frame()

        app = self.get_app(context)

        self.push_call(context, td, widget_app)
        if self._let_dst:
            context[self._let_dst] = let_map

        if self.has_parameter('template'):
            template = app.resolve_templates(self.template(context), check=True)
        else:
            template = widget_app.resolve_templates(self._template(context), check=True)
        template_node = content.add_template(self._tag_name,
                                             template,
                                             app=widget_app)

        yield_stack = context.set_new_call('._yield_stack', list)
        yield_stack.append(lambda c, data: on_yield(c, app, content, self, data))
        try:
            if self.widget_element.has_children:
                yield DeferNodeContents(self.widget_element)
        finally:
            yield_stack.pop()
            scope = context.obj
            self.pop_call(context)

        if self._container and self.has_children:
            with content.node():
                yield DeferNodeContents(self)

        if '_return' in scope:
            scope = scope['_return']
            if hasattr(scope, 'get_return_value'):
                scope = scope.get_return_value()
            if not scope:
                scope = {}
            if not hasattr(scope, 'items'):
                self.throw('widget.return-no-dict',
                           'the return value from a widget must be a dict, or None (not {})'.format(context.to_expr(scope)))

        template_node.update_template_data(scope)
        if cachekey is not None:
            html = template_node.moya_render(self.archive, context, 'html', {})
            cache = self.archive.get_cache('fragment')
            cache.set(cachekey, html, cachefor)


class WidgetBaseContainer(WidgetBase):
    _container = True


class WidgetYield(LogicElement):
    """Yield to a widget block"""

    class Help:
        synopsis = "yield to code block in a widget"

    obj = Attribute("Data to yield", type="expression", required=False, default=None)

    def logic(self, context):
        yield_call = context.get_stack_top('yield')
        yield_data = self.obj(context) or {}
        yield_data.update(self.get_let_map(context))
        if callable(yield_call):
            for node in yield_call(context, yield_data.copy()):
                yield node


class Widget(ElementBase):
    """Create a widget"""

    class Help:
        synopsis = "create a re-uasable widget"

    ns = Attribute("XML Namespace", required=False)
    name = Attribute("Tag name", required=True)
    template = Attribute("Template", type="templates", required=False, default=None)
    let = Attribute("Let destination", required=False, default=None)
    container = Attribute("Is this widget a container?", type="boolean", default=True, required=False)
    synopsis = Attribute("Short description of the widget")
    undocumented = Attribute("Set to yes to disabled documentation for this tag", type="boolean", default=False)
    text = Attribute("Include text children?", type="boolean", default=True)

    cachekey = Attribute("Cache key", name="cachekey", type="text", default=None, required=False)
    cachefor = Attribute("Cache time", name="cachefor", type="timespan", default=None, required=False)

    def finalize(self, context):
        params = self.get_parameters(context)

        attributes = {}
        attributes['template'] = Attribute('Override widget template', name="template", type="templates", required=False, default=None)

        for signature in self.children("signature"):
            for attribute_tag in signature.children("attribute"):
                param_map = attribute_tag.get_all_parameters(context)
                if attribute_tag.has_parameter('default') and not attribute_tag.has_parameter('required'):
                    param_map['required'] = False
                description = attribute_tag.doc
                name = param_map.pop('name')
                attribute = Attribute(description, name=name, evaldefault=True, **param_map)
                attributes[attribute.name] = attribute

        #if 'from' not in attributes:
        attributes['from'] = Attribute("Application", name="from", type="application", map_to="from", default=None)

        doc = None
        for doc_tag in self.children("doc"):
            doc = doc_tag.text.strip()
        meta = Meta()
        meta.is_call = True

        class Help(object):
            synopsis = params.synopsis
            undocumented = params.undocumented

        cls_dict = dict(__doc__=text_type(doc or ''), Meta=meta, Help=Help)
        if self.source_line:
            definition = "%s (line %s)" % (self._location, self.source_line)
        else:
            definition = self._location

        cls_dict['_definition'] = definition
        cls_dict['_template'] = self.template
        cls_dict['_let_dst'] = params.let

        if self.has_parameters('cachekey', 'cachefor'):
            cls_dict['_cache'] = (self.cachekey, self.cachefor)
        else:
            cls_dict['_cache'] = (None, None)

        cls_dict['xmlns'] = params.ns or self.lib.namespace or namespaces.default
        cls_dict.update(('_attribute_' + k, v)
                        for k, v in attributes.items())
        if params.text:
            cls_dict['Meta'] = WidgetBase.Meta
        else:
            cls_dict['Meta'] = WidgetBase.NoTextMeta
        cls_dict['_registry'] = self.archive.registry

        if params.container:
            bases = (WidgetBaseContainer,)
        else:
            bases = (WidgetBase,)

        tag_class = type(py2bytes(params.name),
                         bases,
                         cls_dict)
        tag_class.widget_element = self
        tag_class.libname = None
        tag_class._definition = definition
        tag_class._lib_long_name = context.get('._lib_long_name', None)


class AttributeTag(ElementBase):
    """Defines an attribute in a [tag]tag[/tag], [tag]data-tag[/tag] or [tag]widget[/tag]."""

    class Help:
        synopsis = "define an attribute in a custom tag"
        example = """
        <datatag name="module">
            <doc>Define a top level admin module</doc>
            <signature>
                <attribute name="slug" required="yes" />
                <attribute name="title" required="yes" />
                <attribute name="description" required="yes" />
                <attribute name="content" type="elementref" required="no" />
            </signature>
        </datatag>

        """

    _element_class = "widget"
    preserve_attributes = ['doc']

    class Meta:
        logic_skip = True
        tag_name = "attribute"

    name = Attribute("Name of the attribute", required=True)
    type = Attribute("Type of the attribute", required=False, default="expression", choices=attributetypes.valid_types)
    required = Attribute("Required", type="boolean", required=False, default=True)
    default = Attribute("Default", required=False, default=None)
    metavar = Attribute("Metavar (identifier used in documentation)", required=False)
    missing = Attribute("Are missing values allowed?", type="boolean", default=True, required=False)
    empty = Attribute("Are empty values allowed?", type="boolean", default=True, required=False)
    choices = Attribute("Valid values for this attribute", type="commalist", default=None, required=False)

    def post_build(self, context):
        self.doc = context.sub(self.text.strip())


class ArgumentTag(ElementBase):
    """
    Defines an argument to a macro.

    The text of this tag should document the purpose of the argument.

    """

    class Help:
        synopsis = "define an argument to a macro"
        example = """
        <macro docname="average">
            <signature>
                <argument name="numbers" required="yes" check="len:numbers gt 0">
                    A list (or other sequence) of numbers
                </argument>
            </signature>
            <return value="sum:numbers / len:numbers" />
        </macro>

        """

    class Meta:
        logic_skip = True
        tag_name = "argument"

    name = Attribute("Name of the attribute", required=True)
    required = Attribute("Is this argument required?", type="boolean", default=True)
    check = Attribute("A boolean expression that the attribute must satisfy", type="function", default=None)
    default = Attribute("A value to use if the argument is not supplied", type="function", default=None)

    def post_build(self, context):
        self.doc = context.sub(self.text.strip())


class ArgumentValidator(object):
    """Checks arguments to a macro call."""

    def __init__(self, context, element):
        self.doc = []
        self.required = []
        self.checks = []
        self.arg_names = set()
        self.defaults = OrderedDict()
        for arg in element.children():
            if arg._element_type != (namespaces.default, 'argument'):
                raise errors.ElementError("{} signature must contain <argument> tags only".format(element.parent), element=element)
            name, required, check, default = arg.get_parameters(context, 'name', 'required', 'check', 'default')
            if arg.has_parameter('default'):
                self.defaults[name] = default
                required = False
            self.arg_names.add(name)
            if required:
                self.required.append(name)
            if check is not None:
                self.checks.append((name, check))
            self.doc.append({"name": name, "required": required, "check": check})
        self.required_set = frozenset(self.required)

    def __repr__(self):
        if self.arg_names:
            return "<validator {}>".format(textual_list(self.arg_names))
        else:
            return "<validator>"

    def check(self, context, arg_map, checked_object):
        for k, default in self.defaults.items():
            if k not in arg_map:
                arg_map[k] = default(context)

        if not self.arg_names.issuperset(arg_map.keys()):
            for k in self.arg_names:
                if k not in arg_map:
                    raise ValueError("'{}' is a required argument to {}".format(k, checked_object))

        for name, check in self.checks:
            try:
                result = check.call(context, arg_map)
            except Exception as e:
                raise ValueError("check failed for argument '{}' with error '{}'".format(name, e))
            if not result:
                raise ValueError("{value} is not a valid value for argument {name}".format(name=name,
                                                                                           value=to_expression(context, arg_map[name])))

    def validate(self, context, element, arg_map):
        for k, default in self.defaults.items():
            if k not in arg_map:
                arg_map[k] = default(context)
        if not self.arg_names.issuperset(arg_map.keys()):
            for k in arg_map:
                if k not in self.arg_names:
                    nearest = nearest_word(k, self.arg_names)
                    if nearest is not None:
                        diagnosis = "Did you mean '{}'?".format(nearest)
                    else:
                        diagnosis = "Valid arguments to this macro are {}.".format(textual_list(sorted(self.arg_names), 'and'))
                    element.throw('argument-error.unknown-argument',
                                  "no argument called '{name}' in {element}'".format(name=k, element=element),
                                  diagnosis=diagnosis)
        if not self.required_set.issubset(arg_map.keys()):
            for name in self.required:
                if name not in arg_map:
                    element.throw('argument-error.required',
                                  "argument '{}' is required in {}".format(name, element),
                                  diagnosis='''You can pass a value for '{name}' with let:{name}="<VALUE>" '''.format(name=name, element=element))
        for name, check in self.checks:
            try:
                result = check.call(context, arg_map)
            except Exception as e:
                element.throw('argument-error.check-error',
                              "check for argument '{}' in {} failed with exception: {}".format(name, element, e),
                              diagnosis="An exception was thrown when evaluating the expression '{}'.\n\n"
                              "This could indicate a programming error in the macro or Moya.".format(check.expression))
            if not result:
                diagnosis_msg = "{value} is not a valid value for argument '{name}'. Check the calling logic is correct."
                element.throw('argument-error.check-failed',
                              '''argument '{}' failed check "{}" in {}'''.format(name, check.expression, element),
                              diagnosis=diagnosis_msg.format(name=name,
                                                             value=to_expression(context, arg_map[name]),
                                                             element=element))


class Signature(ElementBase):
    """
    Begins a list of attributes and arguments for a [tag]tag[/tag], [tag]data-tag[/tag], [tag]macro[/tag] or [tag]command[/tag].

    In the case of tags, the signature should contain [tag]attribute[/tag] tags.
    Macros expect [tag]argument[/tag] tags.
    For a command, the signature should contain [tag]arg[/tag] and [tag]option[/tag] tags.

    """
    _element_class = "widget"

    class Help:
        synopsis = "define the attributes / arguments to a tag / macro"
        example = """
        <tag name="fib">
            <doc>Calculate the fibonacci sequence</doc>
            <signature>
                <attribute name="count" type="integer" />
            </signature>
            <let fib="[0, 1]"/>
            <repeat times="count - 2">
                <append value="fib[-1] + fib[-2]" dst="fib" />
            </repeat>
            <return value="fib" />
        </tag>

        """

    class Meta:
        logic_skip = True

    def get_validator(self, context):
        return ArgumentValidator(context, self)

    def finalize(self, context):
        if self.parent._element_type in ((namespaces.default, 'macro'), (namespaces.default, 'Filter')):
            self.validator = ArgumentValidator(context, self)
        else:
            self.validator = None


class Doc(ElementBase):
    """
    Write documentation for a widget or custom tag.

    """
    _element_class = "doc"

    class Meta:
        logic_skip = True

    class Help:
        synopsis = "document a tag"
        example = """
        <widget name="post" template="post.html">
            <doc>Renders a single post</doc>
            <!-- widget code -->
        </widget>

        """
