from __future__ import unicode_literals
from __future__ import print_function

from datetime import datetime
import mimetypes

from fs.path import basename
from fs.errors import FSError

from .response import MoyaResponse
from .compat import PY2, py2bytes
from . import http
from .tools import md5_hexdigest
from . import logic
from . import __version__


SERVER_NAME = "Moya/{}.{}".format(*__version__.split('.')[:2])


def serve_file(req, fs, path, filename=None):
    """Serve a static file"""
    res = MoyaResponse()
    mime_type, encoding = mimetypes.guess_type(basename(path))
    if mime_type is None:
        mime_type = b"application/octet-stream" if PY2 else "application/octet-stream"

    # File does not exist
    if not path or not fs.isfile(path):
        raise logic.EndLogic(http.RespondNotFound())

    serve_file = None
    # Get file info
    try:
        info = fs.getdetails(path)
        serve_file = fs.open(path, 'rb')
    except FSError:
        # Files system open failed for some reason
        if serve_file is not None:
            serve_file.close()
        raise logic.EndLogic(http.RespondNotFound())
    else:
        # Make a response
        file_size = info.size
        mtime = info.modified or datetime.utcnow()
        res.date = datetime.utcnow()
        res.content_type = py2bytes(mime_type)
        res.last_modified = mtime
        res.etag = "{}-{}-{}".format(mtime, file_size, md5_hexdigest(path))
        res.server = SERVER_NAME
        if filename is not None:
            res.content_disposition = 'attachment; filename="{}"'.format(filename)

        # Detect 304 not-modified
        status304 = False
        if req.if_none_match and res.etag:
            status304 = res.etag in req.if_none_match
        elif req.if_modified_since and res.last_modified:
            status304 = res.last_modified <= req.if_modified_since
        if status304:
            res.status = 304
            serve_file.close()
        else:
            # Use high performance file wrapper if available
            if 'wsgi.file_wrapper' in req.environ:
                res.app_iter = req.environ['wsgi.file_wrapper'](serve_file)
            else:
                res.body_file = serve_file
        # Set content length
        if not status304:
            res.content_length = file_size
    raise logic.EndLogic(res)
