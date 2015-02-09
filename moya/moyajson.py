from __future__ import absolute_import
import json


class _MoyaEncoder(json.JSONEncoder):
    """A customer encoder for Moya objects"""
    def default(self, obj):
        if hasattr(obj, '__moyajson__'):
            return obj.__moyajson__()
        return super(_MoyaEncoder, self).default(obj)


def dumps(obj, *args, **kwargs):
    """Allows objects to define how they are serialized to JSON,
    if an object contains a '__moyajson__' method, that will be called and the
    result will be encoded rather than the instance"""
    return json.dumps(obj, cls=_MoyaEncoder, *args, **kwargs)


loads = json.loads
