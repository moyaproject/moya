from __future__ import unicode_literals
from __future__ import absolute_import

from ..elements.elementbase import LogicElement, Attribute
from ..tags.context import DataSetter
from .. import logic
from .. import http
from .. import serve
from .. import errors
from ..compat import text_type, PY2, py2bytes, urlencode, urlparse, parse_qs, urlunparse
from ..request import ReplaceRequest
from ..response import MoyaResponse
from ..urlmapper import MissingURLParameter, RouteError


import json

import logging
log = logging.getLogger('moya.runtime')


class ResponseTag(DataSetter):
    """Create a response object"""

    class Help:
        synopsis = "create a response object"

    class Meta:
        tag_name = "response"

    status = Attribute("Status code", type="httpstatus", required=False, default=200)
    content_type = Attribute("Content Type", default="text/html; charset=UTF-8")
    body = Attribute("Response body", type="expression", default=None)
    charset = Attribute("Character set", default="utf-8")
    headers = Attribute("Headers", type="dict", default=None)

    def get_value(self, context):
        let_map = self.get_let_map(context)
        (status,
         content_type,
         body,
         charset,
         headers) = self.get_parameters(context,
                                        'status',
                                        'content_type',
                                        'body',
                                        'charset',
                                        'headers')
        text = None
        if body is None:
            text = context.sub(self.text)
        response = MoyaResponse(status=status,
                                content_type=py2bytes(content_type),
                                body=body,
                                text=text,
                                charset=py2bytes(charset))
        for k, v in let_map.items():
            try:
                setattr(response, k, v)
            except:
                self.throw("bad-value.response-value",
                           "Can't set {} to {}".format(context.to_expr(k), context.to_expr(v)))
        if headers:
            response.headers.update(headers)
        return response


class Serve(LogicElement):
    """
    This tag serves a response object, which may be created with the [tag]response[/tag].

    """

    class Help:
        synopsis = "serve a response object"
        example = """
        <url route="/test/">
            <response status="im_a_teapot" dst="teapot_response">
                Short and Stout
            </response>
            <serve response="teapot_response" />
        </url>
        """

    response = Attribute("Response object to serve", type="expression", required=True)

    def logic(self, context):
        response = self.response(context)
        raise logic.EndLogic(response)


class ServeFile(LogicElement):
    """Serve a static file."""

    class Help:
        synopsis = "serve a file"
        example = """
        <serve-file fs="static" path="/images/logo.jpg />
        """

    path = Attribute("Path in filesystem", required=True)
    fsobj = Attribute("Filesystem object", type="Index")
    fs = Attribute("Filesystem name")
    ifexists = Attribute("Only serve a response if the file exists", type="boolean")
    name = Attribute("Name of the file", required=False, default=None)

    def logic(self, context):
        params = self.get_parameters(context)

        if params.fsobj is not None:
            fs = params.fsobj
        else:
            try:
                fs = self.archive.filesystems[params.fs]
            except KeyError:
                self.throw("serve.no-fs", "No filesystem called '{}'".format(params.fs))

        path = params.path

        if params.ifexists and not fs.isfile(path):
            return

        req = context.root["request"]
        serve.serve_file(req, fs, path, name=params.name)


class ServeJSON(LogicElement):
    """Serve an object encoded as JSON"""

    class Help:
        synopsis = """serve an object as JSON"""

    obj = Attribute("Object to build JSON from", type="index", required=False, default=None, missing=False)
    indent = Attribute("Indent to make JSON more readable", required=False, default=4)

    def logic(self, context):
        if self.has_parameter('obj'):
            obj = self.obj(context, context)
            json_obj = json.dumps(obj, indent=self.indent(context))
        else:
            json_obj = context.sub(self.text)
        response = MoyaResponse(content_type=b'application/json' if PY2 else 'application/json',
                                body=json_obj)
        raise logic.EndLogic(response)


class ServeXML(LogicElement):
    """Serve XML"""

    class Help:
        synopsis = """serve xml"""

    obj = Attribute("A string of XML, or an object that may be converted to XML", type="expression", required=True, missing=False)
    content_type = Attribute("Mime type", default="application/xml")

    def logic(self, context):
        params = self.get_parameters(context)
        mime_type = params.content_type
        xml = params.obj

        if hasattr(xml, '__xml__'):
            try:
                xml = xml.__xml__()
            except Exception as e:
                self.throw('serve-xml.fail', 'failed to covert {} to XML ({})'.format(context.to_expr(xml), e))

        if not isinstance(xml, bytes):
            xml = text_type(xml)
            xml_bytes = xml.encode('utf-8')
        else:
            xml_bytes = xml
        response = MoyaResponse(content_type=py2bytes(mime_type), body=xml_bytes)
        raise logic.EndLogic(response)


class NotFound(LogicElement):
    """Respond to the request with a '404 not found' response"""

    class Help:
        synopsis = "serve a '404 not found' response"

    def logic(self, context):
        raise logic.EndLogic(http.RespondNotFound())


class Forbidden(LogicElement):
    """Respond to the request with a '403 forbidden' response"""

    class Help:
        synopsis = "respond with a forbidden response"

    def logic(self, context):
        raise logic.EndLogic(http.RespondForbidden())


class RedirectTo(LogicElement):
    """Redirect to new location."""

    class Help:
        synopsis = "redirect to a new location"
        example = """
    <redirect-to url="http://www.moyaproject.com" />
    <redirect-to path="../newuser?result=success" />
    """

    url = Attribute("Destination URL", metavar="URL", required=False, default=None)
    path = Attribute("New path portion of the url, may be relative", metavar="PATH", required=False)
    code = Attribute("HTTP response code (use 301 for permanent redirect)", metavar="HTTPCODE", required=False, default=303, type="httpstatus")
    query = Attribute("Mapping expression to use as a query string", metavar="EXPRESSION", required=False, default=None, type="expression")
    fragment = Attribute("Fragment component in url")

    def logic(self, context):
        (url,
         path,
         query,
         fragment) = self.get_parameters(context,
                                         'url',
                                         'path',
                                         'query',
                                         'fragment')

        if url is not None:
            parsed_url = urlparse(url)
            url = urlunparse(parsed_url[0:3] + ('', '', ''))
            url_query = parsed_url.query
            query_components = parse_qs(url_query)
        else:
            query_components = {}

        request = context['.request']

        query_components.update(self.get_let_map(context))

        if query:
            query_components.update(query)
        if query_components:
            qs = urlencode(query_components, True)
            url += '?' + qs

        if url is not None:
            location = url
        elif path is not None:
            location = request.relative_url(path)
        if fragment:
            location = "{}#{}".format(location, fragment)
        self.new_location(context, location)

    def new_location(self, context, location):
        code = self.code(context)
        response = MoyaResponse(status=code)
        response.location = location
        raise logic.EndLogic(response)


class Redirect(LogicElement):
    """Redirect to a mounted URL"""

    class Help:
        synopsis = "redirect to a named URL"

    name = Attribute("URL name", required="y")
    _from = Attribute("Application", type="application", default=None)
    code = Attribute("HTTP response code (use 301 for permanent redirect)", metavar="HTTPCODE", required=False, default=303, type="integer")
    query = Attribute("Mapping expression to use as a query string", metavar="EXPRESSION", required=False, default=None, type="expression")
    fragment = Attribute("Fragment component in url")

    def logic(self, context):
        (urlname,
         query,
         fragment) = self.get_parameters(context,
                                         'name',
                                         'query',
                                         'fragment')
        app = self.get_app(context)

        if not app:
            raise errors.AppMissingError()

        app_name = app.name
        url_params = self.get_let_map(context)
        try:
            url = context['.server'].get_url(app_name, urlname, url_params)
        except MissingURLParameter as e:
            self.throw('redirect.missing-parameter', text_type(e))
        except RouteError as e:
            self.throw('redirect.no-route', text_type(e))

        if query:
            qs = urlencode(list(query.items()), True)
            url += '?' + qs

        location = url
        if fragment:
            location = "{}#{}".format(location, fragment)

        self.new_location(context, location)

    def new_location(self, context, location):
        code = self.code(context)
        response = MoyaResponse(status=code)
        response.location = location
        raise logic.EndLogic(response)


class Rewrite(Redirect):
    """
    This tag tells Moya to serve the content from a different named URL.

    Note, that unlike [tag]redirect[/tag], this does not involve an extra request.

    """

    class Help:
        synopsis = "serve response from a different named URL"

    code = None

    def new_location(self, context, location):
        url = urlparse(location)
        request = context['.request']
        new_request = request.copy()
        new_request.environ['QUERY_STRING'] = url.query
        new_request.environ['PATH_INFO'] = url.path
        log.debug('rewriting url to %s', location)
        raise logic.EndLogic(ReplaceRequest(new_request))


class RewriteTo(RedirectTo):
    """
    This tag tells Moya to serve the content from a different URL.

    Note, that unlike [tag]redirect-to[/tag], this does not involve an extra request.

    """

    code = None

    class Help:
        synopsis = """serve response from a different location"""

    def new_location(self, context, location):
        url = urlparse(location)
        request = context['.request']
        new_request = request.copy()
        new_request.environ['QUERY_STRING'] = url.query
        new_request.environ['PATH_INFO'] = url.path
        log.debug('rewriting url to %s', location)
        raise logic.EndLogic(ReplaceRequest(new_request))


class SetHeader(LogicElement):
    """
    Add additional headers to the outgoing response.

    """

    header = Attribute("Header name", required=True)
    value = Attribute("Header Value", required=False, default='')

    class Help:
        synopsis = "add additional headers"
        example = """
        <set-header header="moya-example">In your headerz</set-header>
        """

    def logic(self, context):
        header, value = self.get_parameters(context, 'header', 'value')
        if not self.has_parameter('value'):
            value = context.sub(self.text).strip()
        headers = context.set_new_call('.headers', dict)
        headers[header] = value
