# coding=utf-8

from __future__ import unicode_literals
from __future__ import print_function

from moya import namespaces
from moya import logic
from moya import errors
from moya.elements.elementbase import LogicElement, ElementBase, Attribute
from moya.template.rendercontainer import RenderContainer
from moya import moyajson
from moya.tools import textual_list, lazystr
from moya.context.tools import to_expression
from moya.compat import string_types, number_types, text_type, PY2
from moya.logic import MoyaException

import json
import itertools
from operator import attrgetter
import logging
import textwrap

from moya.response import MoyaResponse as Response
from collections import namedtuple


log = logging.getLogger('moya.jsonrpc')


class ErrorCode(object):
    """Enumeration of error codes"""

    parse_error = -32700
    invalid_request = -32600
    method_not_found = -32601
    invalid_params = -32602
    internal_error = -32603

    to_str = {-32700: "Parse error",
              -32600: "Invalid Request",
              -32601: "Method not found",
              -32602: "Invalid params",
              -32603: "Internal error"}


RPCErrorReturnBase = namedtuple('RPCErrorReturn', ["code", "message", "data"])


class RPCErrorReturn(RPCErrorReturnBase):
    def __moyarepr__(self, context):
        if self.message:
            return '''<rpcerror #{}> "{}"'''.format(self.code,
                                                    self.message)
        else:
            return '''<rpcerror #{}>'''.format(self.code)


class ParamError(Exception):
    pass


class MissingParam(ParamError):
    pass


class InvalidParam(ParamError):
    def __init__(self, param, value):
        value_type = _get_type_name(value)
        msg = "parameter '{}' should be type {}, not type {}".format(param.name,
                                                                     param.type,
                                                                     value_type)
        super(InvalidParam, self).__init__(msg)


class InvalidParamDefault(ParamError):
    diagnosis = """The default value set on an <rpc:parameter> must match the 'type' attribute."""

    def __init__(self, param):
        msg = "unable to convert default value ({default}) on  parameter '{name}' to type {type}"
        msg = msg.format(name=param.name, default=param.default, type=param.type)
        super(InvalidParamDefault, self).__init__(msg)


class Param(object):
    valid_param_types = ["string", "number", "bool", "list", "object", "anything"]

    def __init__(self, name, type, default=None, null=False, required=False, doc=None):
        #assert type in self.valid_param_types
        self.name = name
        self.type = type
        self.default = default
        self.null = null
        self.required = required
        self.doc = doc or ''
        super(Param, self).__init__()

    def __repr__(self):
        return "<{name} ({type})>".format(**vars(self))

    def process(self, context, params):
        if self.type not in self.valid_param_types:
            raise ValueError("not a valid parameter type")
        try:
            value = params[self.name]
        except KeyError:
            if self.required:
                raise MissingParam("'{}' is a required parameter".format(self.name))
            #return self.make_default(context)
            return self.default
        if self.null and value is None:
            return value
        return getattr(self, 'check_' + self.type)(value)

    def check(self, value):
        return getattr(self, 'check_' + self.type)(value)

    # def make_default(self, context):
    #     try:
    #         if self.type == "string":
    #             return context.sub(self.default)
    #         else:
    #             return context.eval(self.default)
    #     except:
    #         raise InvalidParamDefault(self)

    def check_string(self, value):
        if not isinstance(value, string_types):
            raise InvalidParam(self, value)
        return value

    def check_number(self, value):
        if not isinstance(value, (bool,) + number_types):
            raise InvalidParam(self, value)
        return value

    def check_bool(self, value):
        return bool(value)

    def check_list(self, value):
        if not isinstance(value, list):
            raise InvalidParam(self, value)
        return value

    def check_object(self, value):
        if not isinstance(value, dict):
            raise InvalidParam(self, value)
        return value

    def check_anything(self, value):
        return value


class Method(object):
    """A single exposed method"""
    def __init__(self, name, group=None, element=None, macro=None, params=None, doc=None, description=None, **kwargs):
        self._name = name
        self.group = group
        self.element = element
        self.macro = macro
        self.params = sorted(params.values(), key=attrgetter('name'))
        self.doc = doc or ''
        self.description = description or ''

    @property
    def name(self):
        if self.group is not None:
            return "{}.{}".format(self.group, self._name)
        else:
            return self._name

    @property
    def base_name(self):
        return self._name

    def __repr__(self):
        return "<method \"{}\" {}>".format(self.name, self.element.libid)

    def process_params(self, context, req_params):
        processed_params = {}
        for param in self.params:
            processed_params[param.name] = param.process(context, req_params)
        return processed_params


class RPCError(Exception):
    def __init__(self, code=ErrorCode.internal_error, message=None, id=None):
        self.code = code
        self.message = message
        self.id = id


class RPCResponse(object):
    pass


class SuccessResponse(RPCResponse):
    def __init__(self, result, id):
        self.result = result
        self.id = id
        super(SuccessResponse, self).__init__()

    def __moyajson__(self):
        response = {"jsonrpc": "2.0",
                    "result": self.result}
        if self.id is not None:
            response["id"] = self.id
        return response

    def __moyarepr__(self, context):
        return to_expression(context, self.result)


class ErrorResponse(RPCResponse):
    def __init__(self, code, message, data=None, id=None):
        self.code = code
        self.message = message
        self.data = data
        self.id = id
        super(ErrorResponse, self).__init__()

    def __repr__(self):
        return "ErrorResponse({!r}, {!r}, {!r}, {!r})".format(self.code,
                                                              self.message,
                                                              self.data,
                                                              self.id)

    def __moyarepr__(self, context):
        return '<rpcerror #{}> "{}"'.format(self.code, self.message)

    def __moyajson__(self):
        error = {"code": self.code,
                 "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        response = {"jsonrpc": "2.0",
                    "id": self.id,
                    "error": error}
        return response


class InvalidResponse(RPCResponse):
    def __init__(self, message):
        self.code = ErrorCode.internal_error
        self.message = message
        self.id = None
        super(InvalidResponse, self).__init__()

    def __repr__(self):
        return "InvalidResponse({!r})".format(self.message)

    def __moyajson__(self):
        error = {"code": self.code,
                 "message": self.message}
        response = {"jsonrpc": "2.0",
                    "error": error}
        return response


CallMethod = namedtuple("CallMethod", ["method", "params", "id", "notification"])


def _get_type_name(obj):
    """Get the name of a type from a json de-serialized object"""
    if isinstance(obj, string_types):
        return "string"
    if isinstance(obj, number_types):
        return "number"
    if isinstance(obj, list):
        return "list"
    if isinstance(obj, bool):
        return "boolean"
    if isinstance(obj, dict):
        return "object"
    if isinstance(obj, type(None)):
        return "null"
    return "unknown"


class Interface(LogicElement):
    """Creates a JSON RPC interface."""
    xmlns = namespaces.jsonrpc
    preserve_attributes = ['_methods']

    errors = Attribute("Optional <enum> of error codes", type="elementref", required=False, default=None)

    class Meta:
        trap_exceptions = True

    class Help:
        synopsis = "create an interface for remote methods"

    def post_build(self, context):
        self._methods = {}
        error_enum_libid = self.errors(context)
        if error_enum_libid is not None:
            enum_element = self.get_element(self.errors(context)).element
            self.errors = self.archive.get_enum(enum_element.libid)
        else:
            self.errors = None

    def logic(self, context):
        pass

    def process_request(self, context, req):
        """Process an individual request"""

        def error_response(*args, **kwargs):
            if notification:
                return None
            else:
                return ErrorResponse(*args, **kwargs)

        if isinstance(req, dict):
            requests = [req]
        else:
            requests = req

        if not isinstance(requests, list):
            yield ErrorResponse(ErrorCode.invalid_request,
                                "Invalid request - list or object expected",
                                id=None)
            return

        if not requests:
            yield ErrorResponse(ErrorCode.invalid_request,
                                "Invalid request",
                                id=None)
            return

        jsonrpc = context['.jsonrpc']
        for req in requests:
            jsonrpc['request'] = req
            if not isinstance(req, dict):
                yield ErrorResponse(ErrorCode.invalid_request,
                                    "Invalid request - object expected",
                                    id=None)
                continue
            notification = 'id' not in req
            if notification:
                req_id = None
            else:
                req_id = req['id']

            if 'jsonrpc' not in req:
                yield error_response(ErrorCode.invalid_request,
                                     "Invalid request - value for 'jsonrpc' expected",
                                     id=req_id)
                continue

            jsonrpc_version = req['jsonrpc']
            if jsonrpc_version != '2.0':
                yield error_response(ErrorCode.invalid_request,
                                     "Invalid request - this server supports only JSON-RPC specification 2.0 (see http://www.jsonrpc.org/specification)",
                                     id=req_id)
                continue

            params = req.get('params', {})
            if not isinstance(params, dict):
                yield error_response(ErrorCode.invalid_params,
                                     "Invalid params - this server only supports parameters by-name",
                                     id=req_id)
                continue

            try:
                method_name = req['method']
            except KeyError:
                yield error_response(ErrorCode.invalid_request,
                                     "Invalid request - value for 'method' expected",
                                     id=req_id)
                continue

            if not isinstance(method_name, string_types):
                yield error_response(ErrorCode.invalid_request,
                                     "Invalid request - 'method' should be a string")
                continue

            if method_name not in self._methods:
                yield error_response(ErrorCode.method_not_found,
                                     "Method not found - no method called '{}'".format(method_name),
                                     id=req_id)
                continue

            method = self._methods[method_name]
            yield CallMethod(method, params, req_id, notification)

    @classmethod
    def log_result(cls, context, result):
        log.debug("= %s", lazystr(to_expression, context, result, max_size=120))

    def run(self, context):
        """Generate a response for either a GET or a POST"""
        request = context['.request']
        app = context.get('.app', None)
        interface_id = "<interface {}#{}>".format(app.name, self.libname)

        if request.method == "GET":
            render_container = RenderContainer.create(app,
                                                      template="moya.jsonrpc/interface.html")
            render_container['interface'] = self
            context['_return'] = render_container
            return
        if request.method != "POST":
            return
        context['.jsonrpc'] = {"request": {}}

        try:
            req = json.loads(request.body.decode('utf-8'))
        except Exception as e:
            log.debug("%s badly formatted JSONRPC request: %s", interface_id, e)
            response = self.make_error(None,
                                       False,
                                       code=ErrorCode.parse_error,
                                       message=text_type(e))
            raise logic.EndLogic(response)

        batch = isinstance(req, list)
        responses = []

        for response in self.process_request(context, req):
            if response is None:
                # Notification
                continue
            elif isinstance(response, ErrorResponse):
                # Problem with request
                responses.append(response)
            elif isinstance(response, CallMethod):
                # Request good, do call
                method, params, req_id, notification = response

                log.debug("%s %s '%s' with %s",
                          interface_id,
                          'notify' if notification else 'call',
                          method.name,
                          lazystr(to_expression, context, params, 80))

                try:
                    params = response.method.process_params(context, params)
                except ParamError as e:
                    response = ErrorResponse(ErrorCode.invalid_params,
                                             text_type(e),
                                             id=req_id)
                    self.log_result(context, response)
                    responses.append(response)
                    continue

                def do_call(element, app, params):
                    try:
                        return_value = self.archive.call(element.libid, context, app, **params)
                    except Exception as e:
                        if isinstance(getattr(e, 'original', None), MoyaException):
                            moya_exc = e.original
                            if moya_exc.type == "jsonrpc.error":
                                return RPCErrorReturn(moya_exc.info['code'],
                                                      moya_exc.info['message'],
                                                      moya_exc.info['data'])
                        error_message = "exception '{}' in rpc call to {}".format(e, method)
                        if hasattr(e, 'moya_trace'):
                            log.error(error_message)
                            if context['.debug'] and context['.console']:
                                context['.console'].obj(context, e)
                            else:
                                error_message = "{}\n{}".format(error_message, e.moya_trace)
                                log.error(error_message)
                        else:
                            context['.console'].obj(context, e)
                            log.exception(error_message)
                        response = ErrorResponse(ErrorCode.internal_error,
                                                 'internal error -- this error has been logged',
                                                 id=req_id)
                        return response
                    else:
                        return return_value

                return_value = do_call(method.element, app, params)

                if method.macro is not None and not isinstance(return_value, (RPCResponse, RPCErrorReturn)):
                    try:
                        macro_app, macro_element = self.get_element(method.macro, app)
                    except Exception as e:
                        log.error("%s no macro called '%s'", interface_id, method.macro)
                        return_value = ErrorResponse(ErrorCode.internal_error,
                                                     "internal error -- this error has been logged",
                                                     id=req_id)
                    else:
                        return_value = do_call(macro_element, app, params)

                if isinstance(return_value, RPCResponse):
                    self.log_result(context, return_value)
                    responses.append(return_value)
                    continue

                if notification:
                    continue

                if isinstance(return_value, RPCErrorReturn):
                    code, message, data = return_value
                    if code.isdigit():
                        code = int(code)
                    else:
                        try:
                            code = int(self.errors[code])
                            if not message:
                                message = self.errors[code].description
                        except Exception as e:
                            log.error("invalid error code '{}' -- defaulting to 'internal_error'".format(code))
                            code = ErrorCode.internal_error
                            message = ErrorCode.to_str[code]

                        return_value = RPCErrorReturn(code, message, data)
                    response = ErrorResponse(code, message, data=data, id=req_id)
                    self.log_result(context, response)
                else:
                    # Check the response is serializable
                    try:
                        moyajson.dumps(return_value)
                    except Exception as e:
                        log.error(text_type(e))
                        response = ErrorResponse(ErrorCode.internal_error,
                                                 'internal error -- server was unable to serialize the response',
                                                 id=req_id)
                        self.log_result(context, response)
                    else:
                        response = SuccessResponse(return_value, req_id)
                        self.log_result(context, return_value)

                responses.append(response)

        if not responses:
            raise logic.EndLogic(Response(content_type=b'application/json' if PY2 else 'application/json'))

        try:
            if batch:
                response_json = moyajson.dumps(responses, indent=4)
            else:
                response_json = moyajson.dumps(responses[0], indent=4)
        except Exception as e:
            log.exception("error serializing response")
            error_response = ErrorResponse(ErrorCode.internal_error,
                                           "server was unable to generate a response -- this error has been logged",
                                           id=None)
            response_json = moyajson.dumps(error_response)

        response = Response(content_type=b'application/json' if PY2 else 'application/json',
                            body=response_json)

        raise logic.EndLogic(response)
        yield  # Because this method should be a generator

    def register_method(self, name, element, macro=None, group=None, params=None, doc=None, description=None, **kwargs):
        """Register an exposed method"""
        method = Method(name,
                        element=element,
                        group=group,
                        macro=macro,
                        params=params,
                        doc=doc,
                        description=description,
                        **kwargs)
        self._methods[method.name] = method

    @property
    def methods(self):
        """Get a list of exposed methods"""
        return [self._methods[name]
                for name in sorted(self._methods.keys())]

    @property
    def methods_by_group(self):
        """Get a list of methods arranged by group"""
        methods = sorted(self._methods.values(), key=lambda m: (m.group, m.base_name.lower()) or '')
        return [(group, list(_methods))
                for group, _methods in itertools.groupby(methods, key=lambda m: m.group)]

    def make_error(self, call_id, notification, code=ErrorCode.internal_error, message=None):
        """Make a JSON-RPC error response"""
        if notification:
            return Response()
        if message is None:
            message = ErrorCode.to_str.get(code, None)
            if message is None:
                message = "unknown error"
        error = {"code": code,
                 "message": message}
        response = {"jsonrpc": "2.0",
                    "error": error,
                    "id": call_id}
        response_json = json.dumps(response, indent=4)
        return Response(content_type=b'application/json' if PY2 else 'application/json',
                        body=response_json)


class Error(LogicElement):
    """Return an rpc error response."""
    xmlns = namespaces.jsonrpc

    class Help:
        synopsis = "return an rpc error"

    code = Attribute("Error code", default="0", map_to="error_code")
    data = Attribute("Optional data regarding the error", type="expression", default=None, required=False)

    def logic(self, context):
        code, data = self.get_parameters(context, 'error_code', 'data')
        error_message = context.sub(self.text.strip())
        self.throw('jsonrpc.error',
                   'JSON RPC error',
                   code=code,
                   message=error_message,
                   data=data)


class SignatureTag(ElementBase):
    """Contains RPC signature"""
    xmlns = namespaces.jsonrpc
    _element_class = "data"

    class Meta:
        tag_name = "signature"
        logic_skip = True


class ParameterTag(ElementBase):
    """Defines a parameter in an RPC call."""
    xmlns = namespaces.jsonrpc
    _element_class = "data"

    _param_types = ['number', "string", "bool", "list", "object", "anything"]

    class Help:
        synopsis = "define an rpc parameter"
        example = """
        <rpc:error code="100" if="format not in ['short', 'medium', 'long', 'full']">
            Format parameter is not correct
        </rpc:error>
        """

    class Meta:
        tag_name = "parameter"
        logic_skip = True

    name = Attribute("Name of the parameter", required=True)
    type = Attribute("Parameter type (number, string, bool, list, object, anything)", required=False, default="anything")
    null = Attribute("Also permit a null value? (None in Moya)", required=False, default=False)
    default = Attribute("Default value", type="expression", required=False)
    required = Attribute("Required?", type="boolean", required=False, default=True)

    def finalize(self, context):
        type = self.type(context)
        if type not in self._param_types:
            raise errors.ElementError("attribute '{}' must be {} (not '{}') ".format('type', textual_list(self._param_types), type),
                                      element=self)


class MethodTag(LogicElement):
    """
    Exposes a single method on a JSON RPC interface.

    This tag should appear within a [tag jsonrpc]interface[/tag], or set the [c]interface[/c] attribute to reference an interface.


    """
    xmlns = namespaces.jsonrpc

    class Meta:
        tag_name = "method"
        trap_exceptions = True

    class Help:
        synopsis = "define a remote method"
        example = """
            <rpc:method name="time">
                <rpc:parameter name="format" type="string" default="medium" required="yes">
                    Time format to return
                </rpc:parameter>
                <return-str>${.now::format}</return-str>
            </rpc:method>
        """

    interface = Attribute("Interface", type="elementref", required=False, default=None)
    name = Attribute("Name of exposed method", required=True)
    group = Attribute("Method group", required=False, default=None)
    description = Attribute("Brief description of method", required=False, default='')
    call = Attribute("Macro to call for functionality", type="elementref", required=False, default=None)

    def run(self, context):
        yield logic.DeferNodeContents(self)

    def lib_finalize(self, context):
        (interface,
         call_macro,
         name,
         group,
         description) = self.get_parameters(context,
                                            'interface',
                                            'call',
                                            'name',
                                            'group',
                                            'description')

        if interface is None:
            try:
                interface = self.get_ancestor((namespaces.jsonrpc, "interface"))
            except:
                raise errors.ElementError("this tag must be inside an <interface>, or specify the 'interface' attribute",
                                          element=self)
        else:
            try:
                interface = self.get_element(interface).element
            except:
                raise errors.ElementError("element '{}' isn't an <interface>".format(interface),
                                          element=self)

        params = {}
        for sig_tag in self.children((namespaces.jsonrpc, 'signature')):
            param_tags = sig_tag.children((namespaces.jsonrpc, "parameter"))
            break
        else:
            param_tags = self.children((namespaces.jsonrpc, "parameter"))

        for param_tag in param_tags:
            try:
                (param_name,
                 _type,
                 default,
                 null,
                 required) = param_tag.get_parameters(context,
                                                      'name',
                                                      'type',
                                                      'default',
                                                      'null',
                                                      'required')
            except Exception as e:
                raise errors.ElementError(text_type(e), element=param_tag)
            if param_tag.has_parameter('default'):
                required = False
            doc = context.sub(param_tag.text.strip())
            _param = params[param_name] = Param(param_name,
                                                _type,
                                                default=default,
                                                required=required,
                                                null=null,
                                                doc=doc)
            # if not required:
            #     try:
            #         _param.make_default(context)
            #     except InvalidParamDefault:
            #         raise errors.ElementError("default '{}' is invalid for type '{}'".format(default, _type),
            #                                   element=param_tag)

        doc = self.get_child('doc')
        if doc is not None:
            doc_text = context.sub(doc.text)
            doc_text = textwrap.dedent(doc_text)
        else:
            doc_text = None

        interface.register_method(name,
                                  self,
                                  macro=call_macro,
                                  group=group,
                                  params=params,
                                  description=description,
                                  doc=doc_text)

    def invoke(self, context):
        pass
