from __future__ import unicode_literals
from __future__ import print_function

from .enum import Enum
from .html import escape
from . import __version__
from .compat import text_type


class StatusCode(Enum):

    def __repr__(self):
        return "<httpstatus %s (%s)>" % (int(self), text_type(self))

    # HTTP Status codes
    # --------------------------------------------------------------------

    # Informational 1xx
    _continue = 100
    switching_protocols = 101

    # Successful 2xxx
    ok = 200
    created = 201
    accepted = 202
    non_authorative_information = 203
    no_content = 204
    reset_content = 205
    partial_content = 206

    # Redirection 3xxx
    multiple_choices = 300
    moved_permanently = 301
    found = 302
    see_other = 303
    not_modified = 304
    use_proxy = 305
    temporary_redirect = 307
    permanent_redirect = 308

    # Client Error 4xx
    bad_request = 400
    unauthorized = 401
    payment_required = 402
    forbidden = 403
    not_found = 404
    method_not_allowed = 405
    not_acceptable = 406
    proxy_authentication_requred = 407
    request_timeout = 408
    conflict = 409
    gone = 410
    length_required = 411
    precondition_failed = 412
    request_entity_too_large = 413
    request_uri_too_long = 414
    unsupported_media_type = 415
    request_range_not_satisfiable = 416
    expectation_failed = 417
    im_a_teapot = 418

    # Server Error 5xx
    internal_error = 500
    no_implemented = 501
    bad_gateway = 502
    service_unavailable = 503
    gateway_timeout = 504
    http_version_not_supported = 505


class RespondWith(object):
    status = StatusCode.ok

    def __init__(self, status=None, headers=None):
        if status is not None:
            # Derivce classes can supply status as class variable
            self.status = status
        self.headers = headers

    def __unicode__(self):
        return get_status_description(self.status)

    def __repr__(self):
        return '<respondwith {} "{}">'.format(self.status, get_status_description(self.status))


class RespondNotFound(RespondWith):
    status = StatusCode.not_found


class RespondForbidden(RespondWith):
    status = StatusCode.forbidden


class RespondUnauthorized(RespondWith):
    status = StatusCode.unauthorized


def get_status_description(status):
    status = StatusCode(status)
    if not status.is_valid():
        return "unknown"
    desc = text_type(status).replace('_', ' ').title()
    return desc

_error_msgs = {
    StatusCode.not_found: "Not Found",
    StatusCode.internal_error: "Internal Error"
}


_standard_html = """<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="content-type" content="text/html;charset=utf-8">
    <title>{status} {msg}</title>
    <style type="text/css">
        body {{font-family: arial,sans-serif;}}
    </style>
</head>
<body>
    <h2>{status} {msg}</h2>
    <pre>Moya was unable to return a response for resource <strong>{path}</strong></pre>
    <hr/>
    <small>Moya {version}</small>
    <small><a href="https://www.moyaproject.com">http://moyaproject.com</a></small>
</body>
"""

_debug_html = """<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="content-type" content="text/html;charset=utf-8">
    <title>{status} {msg}</title>
    <style type="text/css">
        body {{font-family: arial,sans-serif;}}
    </style>
</head>
<body>
    <h2>{status} {msg}</h2>
    <pre>Moya was unable to return a response for resource <strong>{path}</strong></pre>
    <p><strong>{error}</strong></p>
    <p><em>Moya was unable to render "{status}.html" in order to display a more detailed response</em></p>

    <pre>{trace}</pre>
    <hr/>
    <small>Moya {version}</small>
    <small><a href="https://www.moyaproject.com">http://moyaproject.com</a></small>
</body>
"""


def standard_response(status, path, error, trace, debug=False):
    """Produces a standard response for a resource if it wasn't handled by the project logic"""
    status = StatusCode(status)
    msg = get_status_description(status)
    if debug:
        html = _debug_html
    else:
        html = _standard_html

    return html.format(version=__version__,
                       status=int(status),
                       path=escape(path),
                       msg=escape(msg),
                       error=escape(text_type(error or '')),
                       trace=escape(text_type(trace or '')))


if __name__ == "__main__":
    print(StatusCode.not_found)
    print(StatusCode("not_found"))
    print(StatusCode(404))
    print(int(StatusCode("not_found")))
    print(StatusCode.choices)
