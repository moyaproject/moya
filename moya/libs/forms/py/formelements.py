from __future__ import unicode_literals
from __future__ import print_function

from moya.elements.elementbase import LogicElement, Attribute
from moya.tags.context import ContextElementBase, DataSetter
from moya import logic
from moya.console import Cell
from moya.containers import OrderedDict
from moya.template.rendercontainer import RenderContainer
from moya.tools import make_id, url_join
from moya import namespaces
from moya.content import push_content, Content, Node
from moya.render import HTML
from moya.request import UploadFileProxy
from moya.compat import iteritems, itervalues, implements_to_string, string_types, text_type
from moya.context.tools import to_expression
from moya import errors
from moya import http
from moya.interface import AttributeExposer

from collections import defaultdict
from itertools import groupby
from operator import attrgetter
from cgi import FieldStorage
import hashlib

import logging
security_log = logging.getLogger('moya.security')


class SelectOption(object):
    def __init__(self, value, text, group=None, help=None, renderable=None):
        self.value = value
        self.text = text
        self.group = group
        self.help = help
        self.renderable = renderable

    def __repr__(self):
        return "<option {} '{}'>".format(self.value, self.text)

    def __iter__(self):
        return iter([self.value, self.text, self.group])


class Field(Node):
    moya_render_targets = ["html"]

    @classmethod
    def _null_process(cls, context, value=None, **kwargs):
        return value

    def __init__(self,
                 app,
                 label,
                 name,
                 fieldname,
                 src,
                 dst,
                 initial,
                 required,
                 visible,
                 hidelabel=False,
                 default=None,
                 multiple=False,
                 template=None,
                 process_value=None,
                 adapt_value=None,
                 style="paragraphs",
                 data=None,
                 **params):
        self.app = app
        self.label = label
        self.hidelabel = hidelabel
        self.name = name
        self.fieldname = fieldname
        self.src = src
        self.dst = dst
        self.initial = initial
        self.required = required
        self.visible = visible
        self.default = default
        self.multiple = multiple
        self.errors = []
        self._value = None
        self._values = None
        self.id = None
        self.current_group = None
        self.process_value = process_value or self._null_process
        self.adapt_value = adapt_value or self._null_process
        self.style = style
        self.template = template
        self.data = data
        self.requiredcheck = True
        self.requiredmsg = ""
        self._choices = []
        self.__dict__.update(params)
        self.is_form_field = True
        super(Field, self).__init__(name)

    def __repr__(self):
        return "<field %s '%s'>" % (self.fieldname, self.name)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
        return self

    @property
    def values(self):
        """Gets the value as a list"""
        # Will massage non lists in to a list of one, and a None value as an empty list
        value = self.value
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return value
        else:
            return [value]

    def get_default(self):
        return None

    def get_context_value(self, context):
        value = context.get(self.name, None)
        if isinstance(value, list) and not self.multiple:
            if value:
                value = value[0]
            else:
                value = None
        return value

    def process_context_value(self, context):
        if self.name not in context:
            return self.default
        value = context.get(self.name, None)
        if value is None:
            return
        if isinstance(value, list) and not self.multiple:
            if value:
                value = value[0]
            else:
                value = None
        return value

    def add_option(self, value, text, group=None, help=None, renderable=None):
        self._choices.append(SelectOption(value, text, group or self.current_group, help, renderable))

    def set_group(self, label):
        self.current_group = label

    @property
    def choices(self):
        return self._choices

    @property
    def groups(self):
        for key, iter_choices in groupby(self._choices, key=attrgetter('group')):
            yield key, list(iter_choices)

    def set_template_base(self, template_base):
        if not self.template:
            self.template = url_join(template_base, 'fields', '%s.html' % self.fieldname)

    @classmethod
    def get_template_path(cls, style, fieldname):
        return url_join("/moya.forms/styles", style, "fields", "%s.html" % fieldname)

    def moya_render(self, archive, context, target, options):
        template = [options.get('template', None)]
        style = options.get('style', None) or self.style
        template.append(self.get_template_path(style, self.fieldname))
        if style is not 'simple':
            template.append(self.get_template_path('simple', self.fieldname))

        r = RenderContainer.create(archive.find_app('moya.forms'),
                                   template=template)
        r['self'] = self
        r['field'] = self
        if self.data is not None:
            r.update(self.data)
        return r.moya_render(archive, context, target, options)


class ErrorContainer(defaultdict):
    def __init__(self, fields):
        self._fields = fields
        super(ErrorContainer, self).__init__(list)

    def __setitem__(self, k, v):
        if isinstance(v, string_types):
            super(ErrorContainer, self).__setitem__(k, [v])
            self._fields[k][0].errors[:] = [v]
        else:
            super(ErrorContainer, self).__setitem__(k, v)
            self._fields[k][0].errors.append(v)


class FormRenderable(object):
    def __init__(self, renderable=None):
        self.renderable = renderable
        self.children = []
        self.parent = None

    def __repr__(self):
        return "<render %s>" % self.renderable

    def add_child(self, renderable):
        node = FormRenderable(renderable)
        self.children.append(node)
        node.parent = self

    def moya_render(self, archive, context, target, options):
        return self.renderable.moya_render(archive, context, target, options)


class RootFormRenderable(FormRenderable):

    def __init__(self, form, template):
        self.form = form
        self.template = template
        super(RootFormRenderable, self).__init__()

    def moya_render(self, archive, context, target, options):
        td = {'form': self.form,
              'self': self}
        engine = archive.get_template_engine('moya')
        rendered = HTML(engine.render(self.template, td, base_context=context))
        return rendered


class Form(AttributeExposer):
    moya_render_targets = ['html']

    __moya_exposed_attributes__ = sorted(['action',
                                          'app',
                                          'bound',
                                          'content',
                                          'id',
                                          'template',
                                          'csrf_check',
                                          'class',
                                          'method',
                                          'csrf',
                                          'csrf_token',
                                          'data',
                                          'element',
                                          'enctype',
                                          'raw_data',
                                          'error',
                                          'errors',
                                          'fail',
                                          'fields',
                                          'legend',
                                          'ok',
                                          'style',
                                          'validated',
                                          'html_id'])

    def __init__(self, element, context, app, style, template, action, method, enctype, csrf=True, _class=None, html_id=None, legend=None):
        super(Form, self).__init__()
        self.element = element
        self.context = context
        self.app = app
        self.style = style
        self.template = template
        self.action = action
        self.method = method
        self.enctype = enctype
        self.csrf = csrf
        setattr(self, 'class', _class)
        self.html_id = html_id

        self._fields = OrderedDict()
        self.bound = False
        self.validated = False
        self.raw_data = {}
        self._data = {}
        self.error = None
        self.errors = ErrorContainer(self._fields)
        self.id = make_id()
        self.current_field_id = 1

        self.legend = element.legend(context) if legend is None else legend

        self.root = RootFormRenderable(self, template)
        self.current_node = self.root
        self.content = Content(app, template)
        self.content.new_section('fields', None)

        self.field_validators = defaultdict(list)
        self.field_adapters = defaultdict(list)
        self.field_applyers = defaultdict(list)

    def add_csrf(self):
        context = self.context
        field_data = {
            'name': '_moya_csrf',
            'fieldname': 'hidden',
            'src': None,
            'dst': None,
            'initial': self.csrf_token,
            'required': True,
            'label': 'csrf',
            'visible': False,
            'type': 'text',
            '_if': True
        }
        field = self.add_field(field_data, template=None)
        content = context['.content']
        context['field'] = field
        content.add_renderable('hiddeninput', field)

    def __repr__(self):
        return "<form '{}'>".format(self.element.libid)

    def reset(self):
        """Reset the form to a blank state"""
        self._data = {}
        self.raw_data = {}
        for field in self.all_fields:
            if not field.name.startswith('_'):
                field.value = None

    @property
    def csrf_token(self):
        """Return a csrf token"""
        context = self.context
        user_id = text_type(context['.session_key'] or '')
        form_id = self.element.libid
        secret = text_type(self.element.archive.secret)
        raw_token = "{}{}{}".format(user_id, secret, form_id).encode('utf-8', 'ignore')
        m = hashlib.md5()
        m.update(raw_token)
        token_hash = m.hexdigest()
        return token_hash

    def validate_csrf(self, context):
        """Validate CSRF token and raise forbidden error if it fails"""
        if not self.csrf:
            return
        if context['.user'] and context['.request.method'] in ('POST', 'PUT', 'DELETE'):
            csrf = self.raw_data['_moya_csrf']
            #csrf = context['.request.POST._moya_csrf']
            if csrf != self.csrf_token:
                request = context['.request']
                if request:
                    security_log.info('''CSRF detected on request "%s %s" referer='%s' user='%s\'''',
                                      request.method, request.url, request.referer, context['.user.username'])
                raise logic.EndLogic(http.RespondForbidden())

    @property
    def csrf_check(self):
        if not self.csrf:
            return True
        context = self.context
        if context['.user'] and context['.request.method'] in ('POST', 'PUT', 'DELETE'):
            csrf = self.raw_data['_moya_csrf']
            #csrf = context['.request.POST._moya_csrf']
            if csrf != self.csrf_token:
                request = context['.request']
                if request:
                    security_log.info('''CSRF detected on request "%s %s" referer='%s' user='%s\'''',
                                      request.method, request.url, request.referer, context['.user.username'])
                return False
        return True

    @property
    def renderables(self):
        return self.root.children

    @property
    def ok(self):
        return bool(self.validated and not self.errors and not self.error)

    @property
    def fail(self):
        return bool(self.errors or self.error)

    @property
    def fields(self):
        return [field_list[0] for field_list in itervalues(self._fields)]

    @property
    def fields_map(self):
        return {k: v[0] for k, v in self._fields.items()}

    def get_value(self):
        return self

    @property
    def data(self):
        return self._data

    def get_data(self, name):
        value = self.data[name]
        if isinstance(value, FieldStorage):
            value = UploadFileProxy(value)
        return value

    @property
    def current_section(self):
        return self

    def on_content_insert(self, content):
        content.merge(self.content)

    def update_field_value(self, name, value):
        for field in self._fields[name]:
            field.value = value

    def set_field_data(self, name, value):
        self._data[name] = value

    def update(self, value_map):
        if value_map:
            for k, v in value_map.items():
                if k in self._fields:
                    self.update_field_value(k, v)
    __moyaupdate__ = update

    def __contains__(self, key):
        return key in self._fields and self._fields[key] is not None

    @property
    def all_fields(self):
        for field_list in itervalues(self._fields):
            for field in field_list:
                yield field

    def add_field(self,
                  params,
                  enctype=None,
                  style=None,
                  template=None,
                  default=None,
                  process_value=None,
                  adapt_value=None,
                  data=None):
        if enctype is not None and self.enctype is None:
            self.enctype = enctype
        style = style or params.pop('style', None) or self.style
        field = Field(self.app,
                      default=default,
                      template=template,
                      process_value=process_value,
                      adapt_value=adapt_value,
                      style=style,
                      data=data,
                      **params)

        field.id = "field{}_{}".format(self.id, self.current_field_id)
        self.current_field_id += 1
        if params.get('name'):
            name = params['name']
            self._fields.setdefault(name, []).append(field)
        return field

    def add_field_validator(self, field_name, element):
        self.field_validators[field_name].append(element)

    def add_field_adapter(self, field_name, element):
        self.field_adapters[field_name].append(element)

    def add_field_applyer(self, field_name, element):
        self.field_applyers[field_name].append(element)

    def get_field_validators(self, field_name):
        return self.field_validators[field_name]

    def get_field_adapters(self, field_name):
        return self.field_adapters[field_name]

    def push_node(self):
        self.current_node = self.current_node.children[-1]

    def pop_node(self):
        self.current_node = self.current_node.parent

    def add_renderable(self, name, renderable):
        self.current_node.add_child(renderable)

    def add_fail(self, field, msg):
        """Add a message to a list of errors for a given field."""
        self._fields[field][0].errors.append(msg)
        self.errors[field].append(msg)

    def set_fail(self, field, msg):
        """Replace the current list of errors for a field."""
        self._fields[field][0].errors[:] = [msg]
        self.errors[field][:] = [msg]

    def __moyaconsole__(self, console):
        if self.bound:
            console.text("Bound form", fg="cyan", bold=True)
        else:
            console.text("Unbound form", fg="blue", bold=True)

        table = []
        for field in self.all_fields:
            if field.value is None:
                v = Cell('None', dim=True)
            else:
                v = field.value
            table.append([field.name, v])
        console.table(table, ['name', 'value'])

        if self.validated:
            if self.errors:
                console.text("Form errors", fg="red", bold=True)
                error_table = [(field, '\n' .join('* %s' % e.strip() for e in _errors))
                               for field, _errors in iteritems(self.errors)]
                console.table(error_table, ["field", "error"])
            else:
                if self.error:
                    console.text('Form error "%s"' % self.error.strip(), fg="red", bold=True)
                else:
                    console.text("Validated, no errors", fg="green", bold=True)

        if not self.csrf_check:
            console.text('CSRF check failed -- form did not originate from here!', fg="red", bold=True)

    def get_initial_binding(self, context):
        binding = {}
        for field in self.all_fields:
            if field.initial is not None:
                value = field.initial
                try:
                    binding[field.name] = field.adapt_value(context, value=value)
                except Exception as e:
                    raise ValueError("unable to bind field value '{}' ({})".format(field.name, e))

        return binding

    def fill(self, obj):
        for field in self:
            field.value = obj.get(field.name, None)

    def get_binding(self, context, bind):
        binding = {}
        if not bind:
            return binding

        with context.data_frame(bind):
            for field in self.all_fields:
                if field.name:
                    binding[field.name] = field.process_context_value(context)
        return binding

    def get_src_binding(self, context, bind_root):
        binding = {}
        with context.frame(bind_root):
            for field in self.all_fields:
                if field.src and field.src in context:
                    value = context[field.src]
                    value = field.process_value(context, value=value)
                    binding[field.name] = value
        return binding

    def bind(self, context, *bindings):
        self.set_data(context, *bindings)
        self.bound = True

    def set_data(self, context, *data):
        for field in self.all_fields:
            for binding in reversed(data):
                if field.name in binding:
                    value = binding[field.name]
                    if value is not None:
                        field.value = self.raw_data[field.name] = value
                        break

    def moya_render(self, archive, context, target, options):
        form_template = self.template
        if form_template is None:
            form_template = "/moya.forms/styles/%s/form.html" % self.style
        self.content.template = form_template
        self.content.td['form'] = self
        return self.content.moya_render(archive, context, target, options)


class Reset(ContextElementBase):
    """
    Resets a form to a blank state.

    """
    xmlns = namespaces.forms

    class Help:
        synopsis = "reset a form"

    src = Attribute("Form source", type="index", default="form", evaldefault=True, map_to="src")

    def logic(self, context):
        form = self.src(context)
        form.reset()


class Bind(ContextElementBase):
    """
    Bind a form to data

    """
    xmlns = namespaces.forms

    class Help:
        synopsis = "Add data to a form"

    bind = Attribute("Object to bind to (typically .request.POST)", type="expression", default=".request.method=='POST' ? .request.POST : None", evaldefault=True, required=False)
    src = Attribute("Source object to fill in fields (the form)", type="expression", default=None)

    def logic(self, context):
        bind, src = self.get_parameters(context, 'bind', 'src')
        if bind is None:
            bind = {}

        let_map = self.get_let_map(context)
        try:
            bind.update(let_map)
        except Exception as e:
            self.throw('moya.forms.bind-fail',
                       'unable to update bind object {} with {} ({})'.format(context.to_expr(bind),
                                                                             context.to_expr(let_map),
                                                                             e))

        form = src
        form.bind(context, bind)


class Get(DataSetter):
    """
    Get a form object.

    """
    xmlns = namespaces.forms

    class Help:
        synopsis = "get a form"
        example = """
        <forms:get form="#form.login" dst="form" />
        """

    bind = Attribute("Object to bind to", type="expression", default=".request.method == 'POST' ? .request.multi.POST : None", evaldefault=True)
    form = Attribute("Form reference", required=True)
    src = Attribute("Source object to fill in fields", type="reference", default=None)
    dst = Attribute("Destination to store form", required=False, default=None)
    style = Attribute("Override form style", required=False, default=None)
    template = Attribute("Override form template", required=False, default=None)
    action = Attribute("Form action", required=False, default=None)
    method = Attribute("Form method", required=False, default="post", choices=['get', 'post'])
    withscope = Attribute("Use current scope?", default=False, type="boolean")
    blank = Attribute("Blank form?", default=False, type="boolean")
    _id = Attribute("Override HTML id attribute", type="text", default=None)
    legend = Attribute("Override form Legend", type="text", default=None)

    def logic(self, context):
        (bind,
         form,
         src,
         dst,
         style,
         template,
         action,
         method,
         withscope,
         blank,
         _id,
         legend) = self.get_parameters(context,
                                       'bind',
                                       'form',
                                       'src',
                                       'dst',
                                       'style',
                                       'template',
                                       'action',
                                       'method',
                                       'withscope',
                                       'blank',
                                       'id',
                                       'legend')
        if withscope:
            scope = context['.call']
        call = self.push_funccall(context)
        try:
            yield logic.DeferNodeContents(self)
            call.update(self.get_let_map(context))

            args, kwargs = call.get_call_params()
            if withscope:
                new_kwargs = scope
                new_kwargs.update(kwargs)
                kwargs = new_kwargs

        finally:
            self.pop_funccall(context)

        app = self.get_app(context)
        form_app, form_element = self.get_element(form, app)
        app = form_app or app

        template = app.resolve_template(template)

        with self.call(context, app, **kwargs) as call:
            (form_style,
             form_template,
             form_action,
             form_method,
             _class,
             enctype,
             csrf,
             form_id) = form_element.get_parameters(context,
                                                    'style',
                                                    'template',
                                                    'action',
                                                    'method',
                                                    'class',
                                                    'enctype',
                                                    'csrf',
                                                    'id')
            style = style or form_style
            template = template or form_template
            action = action or form_action
            html_id = _id or form_id
            if not self.has_parameter('method'):
                method = form_method
            if action is None:
                action = context['.request.path']

            context['_return'] = form = Form(form_element,
                                             context,
                                             app,
                                             style=style,
                                             template=template,
                                             action=action,
                                             method=method,
                                             enctype=enctype,
                                             _class=_class,
                                             csrf=csrf,
                                             html_id=html_id,
                                             legend=legend)
            context['_content'] = form

            extends = [form_element]
            el = form_element
            visited = {}

            while 1:
                extend = el.extends(context)
                if not extend:
                    break
                parent_el = el
                app, el = el.get_element(extend)
                if (app, el.libid) in visited:
                    raise errors.ElementError("Recursive form extends, element {} has already been extended".format(el),
                                              element=self,
                                              diagnosis="This form has circular references. i.e. the extend attribute references a form that has already been extended.")
                visited[(app, el.libid)] = parent_el
                if not style:
                    style = el.style(context)
                if not template:
                    template = el.template(context)
                if not action:
                    action = el.action(context)
                extends.append(el)
            form.style = style or "simple"
            form.template = template
            form.action = action or ""

            with push_content(context, form.content):
                with form.content.section('fields'):
                    if csrf:
                        form.add_csrf()
                    for el in reversed(extends):
                        yield logic.DeferNodeContents(el)

        if call.has_return:
            form = call.return_value
            bindings = []
            try:
                initial_binding = form.get_initial_binding(context)
            except ValueError as e:
                raise errors.ElementError(text_type(e),
                                          element=self)
            if initial_binding:
                bindings.append(initial_binding)
            if src and context[src]:
                bindings.append(form.get_src_binding(context, src))
            if bind and not blank:
                binding = form.get_binding(context, bind)
                bindings.append(binding)
            if bindings:
                if bind is None:
                    form.set_data(context, *bindings)
                else:
                    form.bind(context, *bindings)
        else:
            form = None
        self.set_context(context, dst, form)


class Validate(LogicElement):
    """
    Validates a form

    If the form is passes all of the validate tests in the form, the Attribute
    'ok' will be True and the containing logic will be execute.

    """
    xmlns = namespaces.forms

    src = Attribute("Form source", type="index", default="form", evaldefault=True, map_to="src", missing=False)
    csrf = Attribute("Enable CSRF check?", type="boolean", default=True)

    class Meta:
        is_call = True
        is_loop = True

    class Help:
        synopsis = "validate a form"

    def logic(self, context):
        form = self.src(context)
        if not form.bound:
            return

        extra_params = self.get_let_map(context)

        extends = [form.element]
        el = form.element
        while 1:
            extend = el.extends(context)
            if not extend:
                break
            app, el = el.get_element(extend)
            extends.append(el)

        values = {name: field.value for name, field in iteritems(form.fields_map)}
        app = self.get_app(context)
        new_values = {}

        if self.csrf(context):
            form.validate_csrf(context)

        for field in form.fields:
            new_values[field.name] = field.value
            if field.requiredcheck and field.required and field.value in ('', None):
                form.add_fail(field.name, field.requiredmsg)
            else:
                for validate_field in form.get_field_validators(field.name):
                    params = extra_params.copy()
                    params.update({
                        "_field": field,
                        "form": form,
                        "value": values[field.name],
                        "values": values,
                        "field": field.value
                    })
                    with self.closure_call(context,
                                           app,
                                           validate_field.data,
                                           **params):
                        yield logic.DeferNodeContents(validate_field.element)

        if not form.errors:
            for field in form.fields:
                if field.adapt_value is not None:
                    value = new_values[field.name]
                    new_value = field.adapt_value(context, value=value)
                    new_values[field.name] = new_value

            for field in form.fields:
                for adapt_field in form.get_field_adapters(field.name):
                    value = new_values[field.name]
                    params = extra_params.copy()
                    params.update({
                        "form": form,
                        "values": values,
                        "value": value
                    })
                    with self.closure_call(context,
                                           app,
                                           adapt_field.data,
                                           **params) as call:
                        yield logic.DeferNodeContents(adapt_field.element)

                    if call.has_return:
                        new_values[field.name] = call.return_value

        for field in form.fields:
            form.set_field_data(field.name, new_values[field.name])

        form.validated = True
        if form.ok:
            #with self.call(context, app, **context.obj) as call:
            yield logic.DeferNodeContents(self)
            if '_return' in context:
                #context['_return'] = call.return_value
                raise logic.Unwind()

            yield logic.SkipNext((namespaces.default, "else"))


class ValidatePost(Validate):
    """
    Validate a form if the current request is a POST request.

    This tag does the same thing as [tag]validate[/tag], but only if the current request is a POST request. Otherwise, the enclosed block will be skipped.

    """

    class Help:
        synopsis = "validate a form for post requests"

    def logic(self, context):
        if context.get('.request.method', '').lower() == 'post':
            for el in super(ValidatePost, self).logic(context):
                yield el


class Apply(LogicElement):
    """
    Applying a form will copy data from a form (in [c]src[/c]) to an object ([c]dst[/c]).

    The name of the values to copy are specified in the [c]dst[/c] attribute of field attributes.

    """
    xmlns = namespaces.forms

    class Meta:
        is_call = True

    class Help:
        synopsis = "apply a form to an object"
        example = """
        <forms:apply src="form" dst="post" />
        """

    src = Attribute("form", type="index", default="form", evaldefault=True)
    dst = Attribute("Destination object", type="reference", required=True, default=None)
    fields = Attribute("fields to apply", type="commalist", default=None)

    def logic(self, context):
        form, dst = self.get_parameters(context, 'src', 'dst')
        if not isinstance(form, Form):
            self.throw('bad-value.form',
                       'form attribute should be a form, not {}'.format(context.to_expr(form)))
        form_data = form.data
        dst_obj = context[dst]
        if not hasattr(dst_obj, 'items'):
            self.throw('moya.forms.bad-dst',
                       "Object referenced by 'dst' must be dict or other mapping type (not {})".format(to_expression(context, dst_obj)))
        if dst:
            field_names = self.fields(context)
            if field_names is None:
                fields = list(form.fields)
            else:
                fields_map = form.fields_map
                fields = [fields_map[name] for name in field_names]

            for field in fields:
                applyers = form.field_applyers[field.name]
                if applyers:
                    for apply_field in applyers:
                        with self.closure_call(context,
                                               form.app,
                                               apply_field.data,
                                               form=form,
                                               object=dst_obj,
                                               values=form.data,
                                               value=form.get_data(field.name)) as call:
                            yield logic.DeferNodeContents(apply_field.element)

                else:
                    with context.frame(dst):
                        field_dst = field.dst
                        if field_dst:
                            value = form_data.get(field.name, None)
                            try:
                                context[field_dst] = value
                            except Exception as e:
                                diagnosis_msg = "The following error was reported: {error}.\n\nCheck you are setting this field to an appropriate value."
                                self.throw('moya.forms.apply-fail',
                                           "unable to set field '{}' to {}".format(field_dst, context.to_expr(value)),
                                           diagnosis=diagnosis_msg.format(error=e),
                                           info={'field': field.name, 'error': text_type(e)})


class FormElement(LogicElement):
    """
    Defines a form.

    """
    xmlns = namespaces.forms

    class Help:
        synopsis = "begin a form definition"
        example = """
        <form libname="form.login" legend="Please login" xmlns="http://moyaproject.com/forms">
            <input name="username" label="Username" type="text" maxlength="30" required="yes"/>
            <password name="password" label="Password" maxlength="30" required="yes"/>
            <submit-button text="Login" />
        </form>
        """

    legend = Attribute("legend text shown above form")
    style = Attribute("Form style", default=None)
    template = Attribute("Form template", default=None)
    action = Attribute("Form action", default=None)
    method = Attribute("Form method", default="post", choices=['get', 'post'])
    enctype = Attribute("Form encoding type", default=None)
    extends = Attribute("Extend another form", default=None)
    _class = Attribute("CSS class override", required=False, default=None)
    csrf = Attribute("Enable csrf protection?", type="boolean", default=True)
    _id = Attribute("Form HTML id", type="text", default=None)

    class Meta:
        tag_name = "form"


@implements_to_string
class FieldElement(LogicElement):
    xmlns = namespaces.forms

    class Help:
        undocumented = True

    enctype = None

    name = Attribute("Field name", required=False, default=None)
    label = Attribute("Label", required=False)
    hidelabel = Attribute("Hide label?", type="boolean", required=False, default=False)
    src = Attribute("Source object index", default=None)
    dst = Attribute("Destination object index", default=None)
    initial = Attribute("Initial value", type="expression", required=False, default=None)
    required = Attribute("Is a value required for this field?", type="boolean")
    requiredcheck = Attribute("Check for required fields?", type="boolean", default="yes")
    requiredmsg = Attribute("Field error text for required fields", type="text", default="This field is required")
    help = Attribute("Help text", required=False, default=None)
    inlinehelp = Attribute("Help text", required=False, default=None)
    template = Attribute("Template", type="template", required=False, default=None)
    visible = Attribute("Visible?", type="boolean", required=False, default=True)
    style = Attribute("Override style", required=False, default=None)
    maxlength = Attribute("Maximum length", type="expression", required=False, default=None)
    adapt = Attribute("Function to adapt field before applying", type="function", default="value", evaldefault=True)
    process = Attribute("Function to process src in to a string", type="function", default="str:value", evaldefault=True)
    disabled = Attribute("Disabled control?", type="boolean", required=False, default=False)
    upload = Attribute("Contains a file upload field?", type="boolean", required=False, default=False)

    def __str__(self):
        return "<%s>" % self._tag_name

    def process_value(self, context, value=None):
        return value

    def get_default(self):
        return None

    def get_field_parameters(self, context):
        params = self.get_all_parameters(context)
        if 'name' in params:
            if params['src'] is None:
                params['src'] = params['name']
            if params['dst'] is None:
                params['dst'] = params['name']
        return params

    def logic(self, context):
        form = context['_return']
        params = self.get_field_parameters(context)
        template = params.pop('template', None)
        style = params.pop('style')

        if params['upload']:
            enctype = "multipart/form-data"
        else:
            enctype = self.enctype

        field = form.add_field(params,
                               enctype=enctype,
                               default=self.get_default(),
                               style=style,
                               process_value=self.process(context),
                               template=template,
                               adapt_value=self.adapt(context),
                               data=self.get_let_map(context))

        content = context['.content']
        context['field'] = field
        if field is not None:
            content.add_renderable(self._tag_name, field)
            with content.node():
                yield logic.DeferNodeContents(self)


class Group(LogicElement):
    """Renders a group of form elements"""
    xmlns = namespaces.forms

    class Help:
        synopsis = "render a group of form elements"

    style = Attribute("Style for child fields", required=False, default=None)

    def logic(self, context):
        form = context['_return']
        params = self.get_parameters(context)
        content = context['.content']

        style = params.style or form.style or 'simple'
        template = "/moya.forms/styles/%s/group.html" % style
        td = {}

        content.add_template("group", template, td)
        with content.node():
            yield logic.DeferNodeContents(self)


class _Field(FieldElement):
    """
    This tag adds a field to the form object, but defers the rendering to enclosed content.

    """

    fieldname = Attribute("Field name", required=False, default="field")

    class Meta:
        synopsis = "add a custom field to a form"
        tag_name = "field"
        example = """
        <field name="example">
            <moya:node template="custom_field.html" />
        </field>
        """

    class Help:
        synopsis = "add a custom field to a form"


class SubmitButton(FieldElement):
    """
    Add a submit button to a form.

    """

    class Help:
        synopsis = "add a submit button in a form"

    fieldname = Attribute("Field name", required=False, default="submit-button")
    name = Attribute("Field name", required=False)
    _class = Attribute("Extra class(es)", required=False, default=None)
    visual = Attribute("Button style", required=False, default="primary")
    block = Attribute("Block level?", required=False, default=False)
    text = Attribute("Text on button", required=False, default="Submit")
    clicked = Attribute("Value when button is clicked", default=None, required=False)


class HiddenInput(FieldElement):
    """
    Add a hidden input to a form.

    """

    class Help:
        synopsis = "add a hidden input value to a form"

    fieldname = Attribute("Field name", required=False, default="hidden")
    visible = Attribute("Visible", type="boolean", required=False, default=False)


class Input(FieldElement):
    """
    Add an input to a form.

    """

    class Help:
        synopsis = "add an input to a form"
        example = """
        <input name="username" maxlength="30" />
        """

    fieldname = Attribute("Field name", required=False, default="text")
    type = Attribute("Input type", required=False, default="text")
    placeholder = Attribute("Placeholder text", required=False, default=None)
    _class = Attribute("Extra class for input", required=False, default="input-medium")


class Upload(FieldElement):
    """
    Add a file upload input to a form.

    """

    class Help:
        synopsis = "add a file upload to a form"

    enctype = "multipart/form-data"

    fieldname = Attribute("Field name", required=False, default="upload")
    type = Attribute("Input type", required=False, default="file")
    placeholder = Attribute("Placeholder text", required=False, default=None)
    _class = Attribute("Extra class for input", required=False, default="")

    def adapt(self, context):

        def process_field_storage(context, value=None):
            if not isinstance(value, FieldStorage):
                return value
            return UploadFileProxy(value)

        return process_field_storage


class Password(FieldElement):
    """
    Add a password input to a form

    """

    class Help:
        synopsis = "add a password field to a form"

    fieldname = Attribute("Field name", required=False, default="password")
    placeholder = Attribute("Placeholder text", required=False, default=None)
    _class = Attribute("Extra class for input", required=False, default="input-medium")


class TextArea(FieldElement):
    """
    Add a textarea (multi-line text input) to a form.

    """

    class Help:
        synopsis = "add a textarea to a form"

    fieldname = Attribute("Field name", required=False, default="text-area")
    placeholder = Attribute("Placeholder text", required=False, default=None)
    rows = Attribute("Number of rows", required=False, default=8, type="integer")
    _class = Attribute("Extra class for input", required=False, default="input-block-level")


class Checkbox(FieldElement):
    """
    Add a checkbox to a form.

    """

    class Help:
        synopsis = "add a checkbox to a form"

    fieldname = Attribute("Field name", required=False, default="check-box")
    on = Attribute("Value when checked", required=False, default="on")
    text = Attribute("Text associated with checkbox", required=False, default='')

    adapt = Attribute("Function to adapt field before applying", type="function", default="value=='on'", evaldefault=True)
    process = Attribute("Function to process src in to a string", type="function", default="value ? 'on' : ''", evaldefault=True)

    def get_default(self):
        return ''


class Radio(FieldElement):
    """
    Add a radio button to a form.

    The user will be able to select just one radio button with the same [c]name[/c] attribute.

    """

    class Help:
        synopsis = "add a radio button to a field"

    fieldname = Attribute("Field name", required=False, default="radio")
    text = Attribute("Text associated with checkbox", required=False, default='')
    on = Attribute("Value when selected", required=True)

    def logic(self, context):
        if '_radiogroup' not in context:
            return super(Radio, self).logic(context)
        radiogroup = context['_radiogroup']
        on = self.on(context)
        text = self.text(context)
        radiogroup.add_option(on or text, text)


class RadioGroup(FieldElement):
    """
    Add a radio group (container for radio buttons) to a form.

    """

    fieldname = Attribute("Field name", required=False, default="radio-group")
    choices = Attribute("Possible choices", type="expression", required=False, default=None)
    inline = Attribute("Display inline?", type="boolean", required=False, default=False)

    class Help:
        synopsis = "add a radio group to a form"
        example = """
        <radio-group name="option" label="Radio Group" required="yes">
            <radio text="Option 1" on="1"/>
            <radio text="Option 2" on="2"/>
            <radio text="Option 3" on="3"/>
        </radio-group>
        """

    @classmethod
    def add_choices(cls, select, select_choices):
        for group, choices in select_choices:
            if choices:
                if isinstance(choices, text_type):
                    select.add_option(group, choices)
                else:
                    for choice, choice_label in choices:
                        select.add_option(choice, choice_label, group=group)

    def logic(self, context):
        form = context['_return']
        params = self.get_field_parameters(context)
        template = params.pop('template', None)
        renderable = context['_radiogroup'] = form.add_field(params,
                                                             template=template)

        select_choices = self.choices(context)

        if select_choices:
            self.add_choices(renderable, select_choices)

        yield logic.DeferNodeContents(self)
        del context['_radiogroup']
        context['.content'].add_renderable(self._tag_name, renderable)


class Select(FieldElement):
    """
    Add a select input to a form.

    """

    class Help:
        synopsis = "add a select box to a form"

    fieldname = Attribute("Field name", required=False, default="select")
    _class = Attribute("Extra class for select", required=False, default="input-medium")
    multiple = Attribute("Multiple select?", required=False, default=False)
    choices = Attribute("Possible choices", type="expression", required=False, default=None)

    @classmethod
    def add_choices(cls, element, select, select_choices):
        """Add choices in a variety of possible formats."""
        try:
            for group_choices in select_choices:
                if isinstance(group_choices, text_type):
                    select.add_option(group_choices, group_choices)
                else:
                    group, choices = group_choices
                    if isinstance(choices, text_type):
                        select.add_option(group, choices)
                    else:
                        for choice, choice_label in choices:
                            select.add_option(choice, choice_label, group=group)
        except Exception as e:
            element.throw('moya.forms.choices-error',
                          'unable to add choices to {}'.format(select),
                          diagnosis="Check the format of your choices. It should a a sequence of (&lt;choice&gt;, &lt;label&gt;).",
                          choices=select_choices)

    def logic(self, context):
        form = context['_return']
        params = self.get_field_parameters(context)
        template = params.pop('template', None)
        select = context['_select'] = form.add_field(params, template=template)

        select_choices = self.choices(context)

        if select_choices:
            self.add_choices(self, select, select_choices)

        yield logic.DeferNodeContents(self)
        del context['_select']
        context['.content'].add_renderable(self._tag_name, select)


class AddChoices(LogicElement):
    """
    Add choices to a [tag]select[/tag] or [tag]check-select[/tag].

    """

    xmlns = namespaces.forms

    class Help:
        synopsis = "add choices to a select tag"

    choices = Attribute("Possible choices", type="expression", required=False, default=None)

    def logic(self, context):
        select = context.get('_select', None)
        if select is None:
            self.throw('add-choices.no-select',
                       'this tag must appear inside a <select>')
        Select.add_choices(self, select, self.choices(context))


class CheckSelect(FieldElement):
    """
    Add a [i]check select[/i] to a form.

    A check select is an alternative to a multiple select ([tag forms]select[/tag]) which uses checkboxes rather than an input.

    """

    fieldname = Attribute("Field name", required=False, default="check-select")
    _class = Attribute("Extra class for select", required=False, default="input-medium")
    choices = Attribute("Possible choices", type="expression", required=False, default=None)

    class Help:
        synopsis = "add a check select control to a form"

    def logic(self, context):
        form = context['_return']
        params = self.get_field_parameters(context)
        params['multiple'] = True
        template = params.pop('template', None)
        select = context['_select'] = form.add_field(params, template=template)

        select_choices = self.choices(context)
        if select_choices:
            Select.add_choices(self, select, select_choices)

        yield logic.DeferNodeContents(self)
        del context['_select']
        context['.content'].add_renderable(self._tag_name, select)


class Option(LogicElement):
    """
    Define an option in a select input.

    """
    xmlns = namespaces.forms
    value = Attribute("Value", default=None, required=False)
    group = Attribute("Group", required=False, default=None)
    selected = Attribute("Selected", type="expression", required=False, default=False)
    help = Attribute("Help text", required=False, default=None)
    renderable = Attribute("Renderable object", type="expression", required=False, default=None)

    class Help:
        synopsis = "an option in a select control"
        example = """
        <select name="fruit">
            <option value="apples">Apples</option>
            <option value="oranges">Oranges</option>
            <option value="pears">Pears</option>
        </select>

        """

    def logic(self, context):
        if '_select' not in context:
            # TODO: Throw an error?
            return
        text = context.sub(self.text.strip())
        if self.has_parameter('value'):
            value = self.value(context)
        else:
            value = text
        params = self.get_parameters(context)
        context['_select'].add_option(value,
                                      text or value,
                                      group=params.group,
                                      help=params.help,
                                      renderable=params.renderable)


class OptGroup(LogicElement):
    """
    Add an optgroup (heading for options) to a select.

    """

    xmlns = namespaces.forms

    label = Attribute("Label", required=True)

    class Help:
        synopsis = "add an optgroup to a select"

    def logic(self, context):
        if '_select' not in context:
            # TODO: Throw an error?
            return

        context['_select'].set_group(self.label(context))
        yield logic.DeferNodeContents(self)
        context['_select'].set_group(None)


class ValidateField(LogicElement):
    """
    Define validation code for a field in a form.

    """
    xmlns = namespaces.forms

    field = Attribute("Field name", required=True, default=None)

    class Meta:
        is_call = True

    class Help:
        synopsis = "validate a field in a form"
        example = """
        <validate-field field="price">
            <fail if="value lte 0>
                Price must be greater than 0.00.
            </fail>
        </validate-field>

        """

    def logic(self, context):
        form = context['_return']
        form.add_field_validator(self.field(context), self.get_closure(context))


class AdaptField(LogicElement):
    xmlns = namespaces.forms

    field = Attribute("Field name", required=True, default=None)

    class Help:
        synopsis = "adapt a field in a form"

    def logic(self, context):
        form = context['_return']
        params = self.get_let_map(context)
        form.add_field_adapter(self.field(context),
                               self.get_closure(context, extra=params))


class ApplyField(LogicElement):
    """
    Apply a form field.

    Invoked by [tag forms]apply[/tag].

    """
    xmlns = namespaces.forms

    class Help:
        synopsis = "apply a form field"

    field = Attribute("Field name", required=True)

    def logic(self, context):
        form = context['_return']
        params = self.get_let_map(context)
        form.add_field_applyer(self.field(context),
                               self.get_closure(context, extra=params))


class Fail(LogicElement):
    """
    Used in a [tag forms]validate-feld[/tag], this tag marks a field as having failed validation, and sets an error message.

    Note that this tag acts like a [tag]return[/tag].

    """

    xmlns = namespaces.forms

    class Meta:
        translate = True

    class Help:
        synopsis = "set a fail in a form validation"
        example = """
        <validate-field field="price">
            <fail if="value lte 0>
                Price must be greater than 0.00.
            </fail>
        </validate-field>
        """

    def logic(self, context):
        field = context['_field'].name
        context['form'].add_fail(field, context.sub(self.text.strip()))
        raise logic.Unwind()


class Actions(LogicElement):
    """
    This tag a group of [tag forms]submit-button[/tag] or other controls that will be rendered as a group (typically a single row).

    """
    xmlns = namespaces.forms

    class Help:
        synopsis = "mark a group of action buttons in a form"
        example = """
        <actions>
            <submit-button name="action" clicked="delete" text="Delete"/>
            <submit-button name="action" clicked="cancel" text="Cancel"/>
        </actions>
        """

    def logic(self, context):
        form = context['_return']
        path = "/moya.forms/styles/%s/actions.html" % form.style
        form.content.add_template(self._tag_name, path, {})

        with form.content.node():
            yield logic.DeferNodeContents(self)


class Error(LogicElement):
    """
    Set an error message on either a field or the entire form.

    """
    xmlns = namespaces.forms

    src = Attribute("Form", default="form", evaldefault=True, type="expression")
    field = Attribute("Field name", required=False, default=None)

    class Meta:
        translate = True

    class Help:
        synopsis = "add an error message to a form"
        example = """
        <forms:error src="form" if=".user">
            You must be logged in to do that!
        </forms:error>

        """

    def logic(self, context):
        field = self.field(context)
        form = self.src(context)
        text = context.sub(self.text)
        if field is None:
            form.error = text
        else:
            form.errors[field] = text
