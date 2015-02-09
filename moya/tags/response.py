from __future__ import unicode_literals
from __future__ import absolute_import

from ..elements.elementbase import LogicElement, Attribute
from ..tags.context import DataSetter
from .. import logic
from .. import http
from ..tools import datetime_to_epoch, md5_hexdigest
from ..context.missing import is_missing
from .. import errors
from ..compat import text_type, PY2, py2bytes, urlencode, urlparse, parse_qs, urlunparse
from ..request import ReplaceRequest
from ..response import MoyaResponse

from fs.path import basename
from fs.errors import FSError

from datetime import datetime
import mimetypes
import time
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
                self.throw("response.badvalue",
                           "Can't set '{}' to {!r}".format(k, v))
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
        <servefile fs="static" path="/images/logo.jpg />
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
        res = MoyaResponse()

        mime_type, encoding = mimetypes.guess_type(basename(path))
        if mime_type is None:
            mime_type = b"application/octet-stream" if PY2 else "application/octet-stream"

        if not path or not fs.isfile(path):
            raise logic.EndLogic(http.RespondNotFound())

        serve_file = None
        try:
            file_size = fs.getsize(path)
            info = fs.getinfokeys(path, 'modified_time')
            serve_file = fs.open(path, 'rb')
        except FSError:
            if serve_file is not None:
                serve_file.close()
            raise logic.EndLogic(http.RespondNotFound())
        else:
            mtime = info.get('modified_time', None)
            if mtime is None:
                mtime = time.time()
            else:
                mtime = datetime_to_epoch(mtime)
            res.date = datetime.utcnow()
            res.content_type = py2bytes(mime_type)
            res.last_modified = mtime
            res.etag = "%i-%i-%s" % (mtime, file_size, md5_hexdigest(path))
            res.server = "Moya/1.0"
            if params.name:
                res.content_disposition = 'attachment; filename="{}"'.format(params.name)

            status304 = False
            if req.if_none_match and res.etag:
                status304 = res.etag in req.if_none_match
            elif req.if_modified_since and res.last_modified:
                status304 = res.last_modified <= req.if_modified_since
            if status304:
                res.status = 304
                serve_file.close()
            else:
                res.body_file = serve_file
            res.content_length = file_size
        raise logic.EndLogic(res)


class ServeJSON(LogicElement):
    """Serve an object encoded as JSON"""

    class Help:
        synopsis = """serve an object as JSON"""

    obj = Attribute("Objecty to __moyajson__", type="index", required=False, default=None)
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

        url_index = ".urls." + app_name + '.' + urlname

        with context.data_frame(url_params):
            try:
                url = context[url_index]
            except:
                self.throw('url.missing',
                           "No named URL called '{}' in application '{}'".format(urlname, app_name),
                           diagnosis="Check for typos in the url name. If you want to redirect to a URL in a different application, set the **from** attribute.",
                           name=urlname,
                           app=app)
            if is_missing(url):
                self.throw('url.missing',
                           "No named URL called '{}' in application '{}'".format(urlname, app_name),
                           diagnosis="Check for typos in the url name. If you want to redirect to a URL in a different application, set the **from** attribute.",
                           name=urlname,
                           app=app)

            url = text_type(context.get(url_index))

        if query:
            qs = urlencode(query.items(), True)
            url += '?' + qs

        location = url
        if fragment:
            location = "{}#{}".format(location)

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
