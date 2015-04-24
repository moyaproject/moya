from __future__ import unicode_literals
from __future__ import print_function

from moya.response import MoyaResponse
from moya.compat import PY2, py2bytes
from moya import http
from moya.tools import datetime_to_epoch, md5_hexdigest
from moya import logic

from fs.path import basename

from datetime import datetime
import mimetypes
import time


def serve_file(req, fs, path, name=None):
    """Serve a file"""
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
        if name is not None:
            res.content_disposition = 'attachment; filename="{}"'.format(name)

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