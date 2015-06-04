from __future__ import unicode_literals

from ..elements.registry import Meta
from ..elements.elementbase import ElementBase, Attribute, LogicElement, MoyaAttributeError
from ..elements.elementproxy import DataElementProxy
from ..logic import DeferNodeContents
from ..tags.context import _LazyCallable, DataSetter
from ..context.missing import is_missing
from ..compat import text_type, py2bytes
from .. import errors


class TagBase(LogicElement):

    def __init__(self, *args, **kwargs):
        self.init_args = (args, kwargs)
        super(TagBase, self).__init__(*args, **kwargs)

    def get_tag_app(self, context):
        app = None
        if self.has_parameter('from'):
            app = self.get_parameter(context, 'from') or None
        if app is None:
            try:
                app = self.archive.get_app_from_lib(self._lib_long_name, current=context['.app'])
            except Exception as e:
                if app is None:
                    self.throw("tag.ambiguous-app",
                               text_type(e),
                               diagnosis="You may need to supply the 'from' attribute")
        return app

    def logic(self, context):
        dst, lazy = self.get_parameters(context, 'dst', 'lazy')
        params = self.get_all_parameters(context)
        if self._let_dst:
            params[self._let_dst] = self.get_let_map(context)
        if '_caller' not in params:
            params['_caller'] = self.get_proxy(context, context['.app'])

        app = self.get_tag_app(context)

        if lazy and dst:
            element_callable = self.archive.get_callable_from_element(self.element, app=app)
            lazy_callable = _LazyCallable(context, element_callable, (), params)
            context.set_lazy(dst, lazy_callable)
        else:
            macro_call = self.push_call(context,
                                        {},
                                        app=app,
                                        yield_element=self,
                                        yield_frame=context.current_frame)
            try:
                macro_call.update(params)
                yield DeferNodeContents(self.element)
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


class Yield(LogicElement):
    """Yield from a tag"""

    class Help:
        synopsis = "yield to code block"

    scope = Attribute("scope to use", type="expression", default=None)

    def logic(self, context):
        scope = self.scope(context)
        if scope is None:
            scope = {}
        scope.update(self.get_let_map(context))

        call = context['.call']

        if is_missing(call) or not call.yield_frame:
            self.throw("yield.cant-yield",
                       "Can't yield from here")

        if scope:
            context.push_frame(call.yield_frame)
            try:
                with context.data_scope(scope):
                    yield DeferNodeContents(call.yield_element)
            finally:
                context.pop_frame()

        else:
            context.push_frame(call.yield_frame)
            try:
                yield DeferNodeContents(call.yield_element)
            finally:
                context.pop_frame()


class GetTagText(DataSetter):
    """
    Get the XML text associated with the parent tag.

    """

    class Help:
        synopsis = "get text from the parent tag"

    sub = Attribute("Substitute the text?", type="boolean", default=False)
    strip = Attribute("Strip text?", type="boolean", default=True)

    def get_value(self, context):
        call = context['.call']

        try:
            element = call.yield_element
        except AttributeError:
            self.throw('get-tag-text.error',
                       "Unable to retrieve tag text here")

        if element is None:
            self.throw('get-tag-text.error',
                       "Unable to detect parent tag")
        text = element.text
        if self.sub(context):
            context.push_frame(call.yield_frame)
            try:
                text = context.sub(text)
            finally:
                context.pop_frame()
        if self.strip(context):
            text = text.strip()
        return text


class Tag(ElementBase):
    """
    Define a custom tag. A custom tag is in a callable tag that works like builtin logic tags. Here's an example of defining a custom tag:

    [code xml]
    <tag name="getstock">
        <doc>Get count of available stock</doc>
        <signature>
            <attribute name="product" />
        </signature>
        <db:get model="#Product.name == product" dst="product"/>
        <return value="product.count"/>
    </tag>
    [/code]

    You may define a custom tag anywhere in a library. Once defined, the tag is available to any code that uses the appropriate namespace defined in [c]lib.ini[/c]. For example, if the above tag is defined in a library with an xml namespace of [c]http://moyaproject.com/sushifinder[/c], it could be invoked with the following file:

    [code xml]
    <moya xmlns:sushifinder="http://moyaproject.com/sushifinder">
        <macro name="main">
            <sushifinder:getstock product="tuna-roll" dst="count" />
            <echo>We have ${count} tuna rolls in stock.</echo>
        </macro>
    </moya>
    [/code]

    Custom tags are preferred over macros when exposing functionality to other libraries.

    """

    class Help:
        synopsis = "define a custom tag"

    ns = Attribute("XML Namespace", required=False, default=None)
    name = Attribute("Tag name", required=True)
    synopsis = Attribute("Short description of tag")
    undocumented = Attribute("Set to yes to disabled documentation for this tag", type="boolean", default=False)
    let = Attribute("Let destination", required=False, default=None)

    _tag_base = TagBase

    def finalize(self, context):
        params = self.get_parameters(context)
        attributes = {}
        try:
            for signature in self.children("signature"):
                for attribute_tag in signature.children("attribute"):
                    param_map = attribute_tag.get_all_parameters(context)
                    if attribute_tag.has_parameter('default') and not attribute_tag.has_parameter('required'):
                        param_map['required'] = False
                    attribute = Attribute(attribute_tag.doc,
                                          map_to=param_map.get('name'),
                                          evaldefault=True,
                                          **param_map)
                    attributes[attribute.name] = attribute
        except MoyaAttributeError as e:
            raise errors.ElementError(text_type(e),
                                      element=self)
        if 'dst' not in attributes:
            attributes['dst'] = Attribute("Destination", name="dst", type="reference", map_to="dst", default=None)
        if 'lazy' not in attributes:
            attributes['lazy'] = Attribute("Enable lazy evaluation", name="lazy", type="boolean", map_to="lazy", default=False)
        attributes['from'] = Attribute("Application", name="from", type="application", map_to="from", default=None)

        doc = None
        for doc_tag in self.children("doc"):
            doc = doc_tag.text.strip()
        meta = Meta()
        meta.is_call = True

        cls_dict = dict(__doc__=text_type(doc or ''), Meta=meta)
        if self.source_line:
            definition = "%s (line %s)" % (self._location, self.source_line)
        else:
            definition = self._location

        class Help(object):
            synopsis = params.synopsis
            undocumented = params.undocumented

        ns = params.ns or self.lib.namespace
        if not ns:
            _msg = 'could not detect namespace for custom tag "{}" -- please specify the namespace with the "ns" attribute or in lib.ini'
            raise errors.ElementError(_msg.format(params.name),
                                      element=self)

        cls_dict.update({'Help': Help,
                         'xmlns': ns,
                         '_registry': self.archive.registry,
                         'element': self,
                         'libname': None,
                         '_definition': definition,
                         '_location': self._location,
                         'source_line': self.source_line,
                         '_code': self._code,
                         '_lib_long_name': context.get('._lib_long_name', None)})
        cls_dict['_let_dst'] = params.let
        cls_dict.update({'_attribute_' + k: v for k, v in attributes.items()})

        tag_class = type(py2bytes(params.name),
                         (self._tag_base,),
                         cls_dict)

        tag_class._definition = definition


class DataTagBase(LogicElement):

    def __init__(self, *args, **kwargs):
        self.init_args = (args, kwargs)
        super(DataTagBase, self).__init__(*args, **kwargs)

    def get_proxy(self, context, app):
        return DataElementProxy(context,
                                app,
                                self,
                                self.get_all_data_parameters(context))

    def finalize(self, context):
        self.archive.add_data_tag(self._element_type, self)


class DataTag(ElementBase):
    """Define a data tag. See [doc customtags]."""

    ns = Attribute("XML Namespace", required=False, default=None)
    name = Attribute("Tag name", required=True)
    synopsis = Attribute("Short description of the data tag")
    undocumented = Attribute("Set to yes to disabled documentation for this tag", type="boolean", default=False)

    _tag_base = DataTagBase

    class Help:
        synopsis = "define a data tag"

    def finalize(self, context):
        params = self.get_parameters(context)
        attributes = {}
        for signature in self.children("signature"):
            for attribute_tag in signature.children("attribute"):
                param_map = attribute_tag.get_all_parameters(context)
                if attribute_tag.has_parameter('default') and not attribute_tag.has_parameter('required'):
                    param_map['required'] = False
                attribute = Attribute(attribute_tag.doc,
                                      map_to=param_map.get('name'),
                                      evaldefault=True,
                                      **param_map)
                attributes[attribute.name] = attribute
        doc = None
        for doc_tag in self.children("doc"):
            doc = doc_tag.text.strip()
        meta = Meta()
        meta.logic_skip = True
        meta.is_call = False

        class Help(object):
            synopsis = params.synopsis
            undocumented = params.undocumented

        cls_dict = dict(__doc__=text_type(doc or ''), Meta=meta, Help=Help)
        if self.source_line:
            definition = "%s (line %s)" % (self._location, self.source_line)
        else:
            definition = self._location

        cls_dict['_definition'] = definition
        cls_dict['xmlns'] = params.ns or self.lib.namespace
        cls_dict.update({'_attribute_' + k: v for k, v in attributes.items()})
        cls_dict['_registry'] = self.archive.registry

        tag_class = type(py2bytes(params.name),
                         (self._tag_base,),
                         cls_dict)
        tag_class.element = self
        tag_class._definition = definition
