from __future__ import unicode_literals
from __future__ import print_function

from ..elements import Attribute
from ..interface import AttributeExposer
from ..tags.context import DataSetter

import requests

import logging
log = logging.getLogger('moya.runtime')


class ResponseProxy(AttributeExposer):
    """Proxy for a request object"""

    __moya_exposed_attributes__ = ["url",
                                   "text",
                                   "status_code",
                                   "headers",
                                   "cookies",
                                   "history",
                                   "content",
                                   "json",
                                   "encoding"]

    def __init__(self, req, url, method):
        self._req = req
        self._url = url
        self._method = method

    def __repr__(self):
        return '<httpresponse {} "{}">'.format(self._method, self._url)

    @property
    def url(self):
        return self._req.url

    @property
    def text(self):
        return self._req.text

    @property
    def status_code(self):
        return self._req.status_code

    @property
    def headers(self):
        return dict(self._req.headers)

    @property
    def cookies(self):
        return dict(self._req.cookies)

    @property
    def history(self):
        self._req.history

    @property
    def content(self):
        return self._req.content

    @property
    def json(self):
        try:
            return self._req.json()
        except:
            return None

    @property
    def encoding(self):
        return self._req.encoding


class RequestTag(DataSetter):
    """
    Make HTTP requests.

    """

    class Meta:
        tag_name = "request"

    class Help:
        synopsis = "make an http request"

    url = Attribute("URL to request", required=True)
    method = Attribute("Method to use", choices=['get', 'post', 'delete', 'put', 'trace', 'head', 'options'], default=None)
    params = Attribute("Request parameters", type="dict", required=False, default=None)
    headers = Attribute("Additional headers", type="dict", required=False, default=None)
    data = Attribute("Data to be form encoded", type="dict", required=False, default=None)
    timeout = Attribute("Timeout in seconds", type="number", required=False, default=None)

    username = Attribute("Username for basic auth", required=False, default=None)
    password = Attribute("Password for basic auth", required=False, default=None)

    def _get_method(self):
        return 'get'

    def logic(self, context):
        params = self.get_parameters(context)
        method = params.method or self._get_method()
        request_maker = getattr(requests, method)
        if not self.has_parameter('params'):
            request_params = self.get_let_map(context)
        else:
            request_params = params.params
        if params.username is not None:
            auth = (params.username, params.password or '')
        else:
            auth = None
        try:
            log.debug('requesting %s %s', method, params.url)
            response = request_maker(params.url,
                                     auth=auth,
                                     timeout=params.timeout,
                                     params=request_params,
                                     headers=params.headers,
                                     data=params.data)
        except requests.exceptions.Timeout:
            self.throw('requests.timeout',
                       'the server did not response in time',
                       diagnosos="Try raising the timeout attribute")
        except requests.exceptions.HTTPError:
            self.throw('requests.http-error',
                       'the server response was not invalid')
        except requests.exceptions.TooManyRedirects:
            self.throw('requests.too-many-redirects',
                       'too may redirect responses')
        except requests.exceptions.RequestException as e:
            self.throw('requests.error',
                       'unable to make request ({})'.format(e))

        response_proxy = ResponseProxy(response, params.url, method)
        self.set_context(context, params.dst, response_proxy)


class RequestGetTag(RequestTag):
    """
    Make a GET request (see [tag]request[/tag]).

    """

    class Help:
        synopsis = "make a get requests"

    class Meta:
        tag_name = "request-get"

    def _get_method(self):
        return 'get'


class RequestPostTag(RequestTag):
    """
    Make a POST request (see [tag]request[/tag]).

    """

    class Help:
        synopsis = "make a post request"

    class Meta:
        tag_name = "request-post"

    def _get_method(self):
        return 'post'
