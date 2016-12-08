from __future__ import unicode_literals
from __future__ import absolute_import

from ..elements.elementbase import LogicElement, Attribute
from ..tags.context import DataSetter
from .. import logic
from .. import http
from .. import serve
from .. import errors
from .. import interface
from .. import urltools
from .. import moyajson
from ..compat import text_type, PY2, py2bytes, urlencode, urlparse, parse_qs, urlunparse, quote_plus
from ..request import ReplaceRequest
from ..response import MoyaResponse
from ..urlmapper import MissingURLParameter, RouteError

from webob.response import Response

from datetime import datetime
import base64
import pytz
import logging

from fs.path import dirname

GMT = pytz.timezone('GMT')
log = logging.getLogger('moya.runtime')


class ResponseTag(DataSetter):
    """Create a response object"""

    class Help:
        synopsis = "create a response object"

    class Meta:
        tag_name = "response"

    status = Attribute("Status code", type="httpstatus", required=False, default=200)
    contenttype = Attribute("Content Type", default="text/html; charset=UTF-8")
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
                                        'contenttype',
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


class Respond(ResponseTag):
    """
    Immediatley return a response.

    Useful for more esoteric status codes.

    """

    class Help:
        synopsis = """serve a response"""
        example = """
        <respond code="im_a_teapot" />
        """

    class Meta:
        tag_name = "respond"

    def logic(self, context):
        response = self.get_value(context)
        raise logic.EndLogic(response)


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
    filename = Attribute("Name of the file being serve", required=False, default=None)

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
        serve.serve_file(req, fs, path, filename=params.filename)


class ServeJSON(LogicElement):
    """

    Serve an object encoded as JSON.

    This tag with either serialize an object ([i]obj[/i]) if provided, or serve the tag text as JSON.

    Like other serve- tags, this will return a response and stop processing the view.

    """

    class Help:
        example = """
        <!-- serialize an object -->
        <serve-json obj="{'status': 'ok'}"/>

        <!-- just serve the contents -->
        <serve-json>
        {
            "crew": ["john", "scorpius"]
        }
        </serv-json>

        """
        synopsis = """serve an object as JSON"""

    obj = Attribute("Object to build JSON from", type="expression", required=False, default=None, missing=False)
    indent = Attribute("Indent to make JSON more readable", type="integer", required=False, default=4)

    def logic(self, context):
        if self.has_parameter('obj'):
            obj = self.obj(context)
            try:
                json_obj = moyajson.dumps(obj, indent=self.indent(context))
            except Exception as e:
                self.throw('serve-json.fail', text_type(e))
        else:
            json_obj = context.sub(self.text)
        response = MoyaResponse(content_type=b'application/json' if PY2 else 'application/json',
                                body=json_obj)
        raise logic.EndLogic(response)


class ServeJsonObject(LogicElement):
    """

    Serve a dict encoded as a JSON object.

    Like other serve- tags, this will return a response and stop processing the view.

    Keys in the json object can be given via the let extension. Here's an example:
    [code xml]
    <serve-json-object let:success="yes" let:message="'upload was successful'"/>
    [/code]

    This will serve the following JSON:
    [code]
    {
        "success": true,
        "message": "upload was successful"
    }
    [/code]

    You can also create the json object as you would a [tag]dict[/tag]. The following returns the same response as above:
    [code xml]
    <serve-json-object>
        <let success="yes"/>
        <let-str msg="upload was successful"/>
    </serve-json-object/>
    [/code]
    """

    class Help:
        synopsis = """serve an dict as JSON"""

    indent = Attribute("Indent to make JSON more readable", type="integer", required=False, default=4)

    def logic(self, context):
        obj = self.get_let_map(context)
        with context.data_scope(obj):
            yield logic.DeferNodeContents(self)

        try:
            json_obj = moyajson.dumps(obj, indent=self.indent(context))
        except Exception as e:
            self.throw('serve-json-object.fail', text_type(e))

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


class Denied(LogicElement):
    """
    Reject basic auth. Generally used in conjunction with [tag]auth-check[/tag].

    """

    realm = Attribute('Basic auth realm', type="text", required=False)

    class Help:
        synopsis = "reject basic authorization"

    def logic(self, context):
        if self.has_parameter('realm'):
            realm = self.realm(context) or 'restricted'
        else:
            realm = context['_realm'] or 'restricted'
        headers = {'WWW-Authenticate': 'Basic realm="{}:"'.format(realm)}
        raise logic.EndLogic(http.RespondUnauthorized(headers=headers))


class AuthCheck(LogicElement):
    """
    Perform a basic auth check.

    This tag returns a 401 response if basic auth isn't supplied.

    If basic auth credentials are included in the request, they are decoded and the enclosed block is executed with the variables [c]username[/c] and [c]password[/c]. The enclosed block can then use the [tag]denied[/tag] tag to reject bad credentials. Here is an example:

    [code xml]
    <auth-check>
        <denied if="[username, password] != ['john', 'iloveaeryn']" />
    </auth-check>
    [/code]

    """

    realm = Attribute('Basic auth realm', type="text", default='restricted')

    class Help:
        synopsis = "perform basic auth check"

    def logic(self, context):
        realm = self.realm(context)
        authorization = context['.request.authorization']
        if not authorization:
            self.denied(realm)

        auth_method, auth = authorization
        if auth_method.lower() != 'basic':
            self.denied(realm)

        try:
            username, _, password = base64.b64decode(auth).partition(':')
        except:
            self.denied(realm)

        if not username or not password:
            self.denied(realm)

        scope = {
            'username': username,
            'password': password,
            '_realm': realm
        }
        with context.data_scope(scope):
            yield logic.DeferNodeContents(self)

    def denied(self, realm):
        headers = {'WWW-Authenticate': 'Basic realm="{}:"'.format(realm)}
        raise logic.EndLogic(http.RespondUnauthorized(headers=headers))


class AdminOnly(LogicElement):
    """
    Respond with a forbidden response if the user is not admin.

    This tag is a shortcut for the following:

    [code xml]
    <forbidden if="not .permissions.admin"/>
    [/code]

    """

    class Help:
        synopsis = "return a forbidden response if the user is not admin"

    def logic(self, context):
        if not context['.permissions.admin']:
            raise logic.EndLogic(http.RespondForbidden())


class RedirectToBase(object):
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


class RedirectTo(RedirectToBase, LogicElement):
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

    def new_location(self, context, location):
        code = self.code(context)
        response = MoyaResponse(status=code)
        response.location = location
        raise logic.EndLogic(response)


class RedirectBase(object):

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
            qs = urltools.urlencode(query)
            # qs = "&".join(["{}={}".format(quote_plus(k), quote_plus(v)) if v is not None else quote_plus(k)
            #                for k, v in query.items()])
            #qs = urlencode(list(query.items()), True)
            url += '?' + qs

        location = url
        if fragment:
            location = "{}#{}".format(location, fragment)

        self.new_location(context, location)


class Redirect(RedirectBase, LogicElement):
    """Redirect to a mounted URL"""

    class Help:
        synopsis = "redirect to a named URL"

    name = Attribute("URL name", required=True, metavar="URL NAME")
    _from = Attribute("Application", type="application", default=None)
    code = Attribute("HTTP response code (use 301 for permanent redirect)", metavar="HTTPCODE", required=False, default="303", type="httpstatus")
    query = Attribute("Mapping expression to use as a query string", metavar="EXPRESSION", required=False, default=None, type="expression")
    fragment = Attribute("Fragment component in url")

    def new_location(self, context, location):
        code = self.code(context)
        response = MoyaResponse(status=code)
        response.location = location
        raise logic.EndLogic(response)


class Rewrite(RedirectBase, LogicElement):
    """
    This tag tells Moya to serve the content from a different named URL.

    Note, that unlike [tag]redirect[/tag], this does not involve an extra request.

    """

    class Help:
        synopsis = "serve response from a different named URL"

    name = Attribute("URL name", required=True, metavar="URL NAME")
    _from = Attribute("Application", type="application", default=None)
    query = Attribute("Mapping expression to use as a query string", metavar="EXPRESSION", required=False, default=None, type="expression")
    fragment = Attribute("Fragment component in url")

    def new_location(self, context, location):
        url = urlparse(location)
        request = context['.request']
        new_request = request.copy()
        new_request.environ['QUERY_STRING'] = url.query
        new_request.environ['PATH_INFO'] = url.path
        log.debug('rewriting url to %s', location)
        raise logic.EndLogic(ReplaceRequest(new_request))


class RewriteTo(RedirectToBase, LogicElement):
    """
    This tag tells Moya to serve the content from a different URL.

    Note, that unlike [tag]redirect-to[/tag], this does not involve an extra request.

    """

    url = Attribute("Destination URL", metavar="URL", required=False, default=None)
    path = Attribute("New path portion of the url, may be relative", metavar="PATH", required=False)
    query = Attribute("Mapping expression to use as a query string", metavar="EXPRESSION", required=False, default=None, type="expression")
    fragment = Attribute("Fragment component in url")

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


class CheckModified(LogicElement):
    """
    Return a not_modifed (304) response if a resource hasn't changed.

    This tag allows a view to skip generating a page if it hasn't changed since the last time a browser requested it.
    To use this tag, set either the [url https://en.wikipedia.org/wiki/HTTP_ETag]etag[/url] parameter, or the [c]time[/c] parameter, which should be the time the page was last modified. Moya will compare these attributes to the request headers, and generate a not modified (304) response if the page hasn't changed. Otherwise the view will continue processing as normal.

    """

    time = Attribute("Time resource was updated", type="expression", required=False)
    etag = Attribute("ETag for resource", type="text", required=False)

    class Help:
        synopsis = "conditionally return a not modified response"
        example = """
        <view libname="view.show_post" template="post.html">
            <db:get model="#Post" let:slug=".url.slug"/>
            <check-modified time="post.updated_date" />
        </view>
        """

    def logic(self, context):
        request = context['.request']

        if request.method not in ["GET", "HEAD"]:
            return
        headers = context.set_new_call('.headers', dict)

        if self.has_parameter('time'):
            _dt = self.time(context)
            dt = interface.unproxy(_dt)
            if not isinstance(dt, datetime):
                self.throw('bad-value.time', "attribute 'time' should be a datetime object, not {}".format(context.to_expr(dt)))
            gmt_time = GMT.localize(dt)
            modified_date = gmt_time.strftime('%a, %d %b %Y %H:%M:%S GMT')
            headers['Last-Modified'] = modified_date
            if request.if_modified_since and gmt_time >= request.if_modified_since:
                response = Response(status=http.StatusCode.not_modified,
                                    headers=headers)
                raise logic.EndLogic(response)

        if self.has_parameter('etag'):
            etag = self.etag(context)
            headers['ETag'] = etag
            if etag in request.if_none_match:
                response = Response(status=http.StatusCode.not_modified,
                                    headers=headers)
                raise logic.EndLogic(response)
