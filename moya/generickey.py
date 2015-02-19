from __future__ import unicode_literals
from __future__ import print_function

from .errors import ElementNotFoundError

from .compat import text_type
import logging
log = logging.getLogger('moya.db')


class GenericKey(object):
    """A generic foreign key"""
    def __init__(self, app, model, pk):
        self.app = app
        self.model = model
        self.pk = pk

    def __repr__(self):
        if self.app is None:
            return "<generic-key (null)>"
        return "<generic-key {}#{} {}>".format(self.app.name, self.model.libname, self.pk)

    @classmethod
    def from_object(cls, obj):
        if obj is None:
            return cls(None, None, None)
        return cls(obj._app, obj._model, obj.id)

    @classmethod
    def decode(cls, value):
        if not value:
            return cls(None, None, None)
        try:
            app, model, pk = [v or None for v in value.split(',')]
            pk = int(pk)
        except ValueError:
            # Malformed generic key in the database
            return cls(None, None, None)
        from moya import pilot
        # TODO: is there a better way of getting the archive here?
        archive = pilot.context['.app'].archive
        app = archive.get_app(app)
        if app is None:
            # No such app, treat it as a null
            return cls(None, None, None)

        try:
            app, model = archive.get_element('{}#{}'.format(app.name, model))
        except:
            # Model doesn't exist, treat it as a null
            return cls(None, None, None)

        any_key = cls(app, model, pk)
        return any_key

    def __moyacontext__(self, context):
        return self.lookup(context)

    def __moyadbobject__(self):
        return self.encode()

    def encode(self):
        if not self.app:
            return None
        return ",".join((self.app.name, self.model.libname, text_type(self.pk)))

    def lookup(self, context):
        if self.app is None:
            return None

        element_ref = '{}#{}'.format(self.app.name, self.model.libname)
        try:
            model_app, model = self.app.archive.get_element(element_ref)
        except ElementNotFoundError:
            log.warning('no model found for generic key {!r}', self)
            return None
        db = model.get_db()
        dbsession = context['._dbsessions'][db.name]
        table_class = model.get_table_class(model_app)
        qs = dbsession.query(table_class).filter(table_class.id == self.pk)
        return qs.first()
