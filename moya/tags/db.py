from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from ..elements.elementbase import (ElementBase, Attribute)
from .. import logic
from .. import errors
from ..db import wrap_db_errors, dbobject
from .. import interface
from ..context import Context
from ..logic import DeferNodeContents, SkipNext
from ..tags import dbcolumns
from ..tags.dbcolumns import no_default
from ..tags.context import DataSetter, ContextElementBase
from ..elements.boundelement import BoundElement
from ..console import make_table_header, Cell
from .. import namespaces
from ..context.expressiontime import ExpressionDateTime
from ..context.missing import is_missing
from ..containers import OrderedDict
from ..dbexpression import DBExpression
from ..template.rendercontainer import RenderContainer
from .. import timezone
from .. import http
from ..compat import text_type, implements_bool, implements_to_string, iteritems, py2bytes, xrange, number_types, string
from .. import pilot

from json import loads
from collections import namedtuple
from random import choice
import uuid
from datetime import datetime

from sqlalchemy import (Table,
                        Column,
                        ForeignKey,
                        Integer,
                        DateTime,
                        desc,
                        UniqueConstraint)

from sqlalchemy.sql import text
from sqlalchemy.orm import mapper, relationship, backref
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound, UnmappedInstanceError
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.engine import RowProxy, ResultProxy
from sqlalchemy import event

import weakref
import logging
log = logging.getLogger('moya.db')

ExtendedDefinition = namedtuple('ExtendedDefinition', ['columns',
                                                       'properties',
                                                       'object_properties',
                                                       'constraints'])


class AdaptValueError(ValueError):
    def __init__(self, msg, k, v):
        super(AdaptValueError, self).__init__(msg)
        self.k = k
        self.v = v


@implements_to_string
class DBValidationError(Exception):

    def __init__(self, msg, diagnosis=None):
        self.msg = msg
        self.diagnosis = diagnosis

    def __str__(self):
        return self.msg


class DBMixin(object):

    def get_model(self, context, model, app):
        try:
            model_app, model = self.get_app_element(model, app=app)
        except errors.ElementNotFoundError as e:
            raise
            raise errors.ElementError(text_type(e), element=self)
        return model_app, model

    def get_session(self, context, db=None):
        if db is None:
            db = self.db(context)
        dbsessions = context.get('._dbsessions', None)
        if dbsessions is None:
            raise logic.MoyaException("db.no-session",
                                      "unable to get database session",
                                      diagnosis="Have you initialized a database in settings?")

        try:
            session = dbsessions[db]
        except KeyError:
            if db == "_default":
                raise logic.MoyaException("db.missing-db", "No database defined".format(db))
            else:
                raise logic.MoyaException("db.missing-db", "No database called '{}'".format(db))
        else:
            return session


@implements_bool
class MoyaQuerySet(interface.AttributeExposer):
    """Context interface for an sqlalchemy query set"""

    __moya_exposed_attributes__ = ['sql',
                                   'first',
                                   'last',
                                   'list',
                                   'count',
                                   'exists']

    def __init__(self, qs, table_class, session):
        self._qs = qs
        self.table_class = table_class
        self.dbsession = session
        self._count = None

    def __repr__(self):
        if self.table_class:
            return "<queryset {!r}>".format(self.table_class._model)
        else:
            return "<queryset>"

    def _get_query_set(self):
        return self._qs

    @wrap_db_errors
    def __iter__(self):
        return iter(self._qs)

    @wrap_db_errors
    def __len__(self):
        return self.count

    @property
    def sql(self):
        return text_type(self._qs.statement)

    @wrap_db_errors
    def slice(self, start, stop, step=None):
        if step is not None:
            raise logic.MoyaException('db.slice-error',
                                      "Querysets do not support slicing with a step")
        if start < 0 or stop < 0:
            raise logic.MoyaException("db.slice-error",
                                      "Querysets do not support negative indexing")
        return MoyaQuerySet(self._qs.slice(start, stop), self.table_class, self.dbsession)

    @wrap_db_errors
    def __bool__(self):
        return self._qs.first() is not None

    @property
    def first(self):
        return self._qs.first()

    @property
    def last(self):
        """Get the last item in the qs"""
        # There doesn't seem to be a more efficient way of doing this
        last = self.count - 1
        return self._qs[last - 1]

    @property
    def list(self):
        return list(self._qs)

    @property
    def count(self):
        if self._count is None:
            self._count = self._qs.count()
            #self._count = sum(1 for _ in self._qs)

            # if self.table_class:
            #     self._count = self.dbsession.query(self.table_class.id).count()
            # else:
            #     self._count = self._qs.count()
        return self._count

    @property
    def exists(self):
        return self._qs.first() is not None

    def in_(self, context, b):
        return self.table_class.id.in_(b)

    def notin_(self, context, b):
        return self.table_class.id.notin_(b)

    def __add__(self, rhs):
        if isinstance(rhs, MoyaQuerySet):
            union_qs = self._qs.order_by(None).union(rhs._qs.order_by(None))
            return MoyaQuerySet(union_qs, self.table_class, self.dbsession)
        else:
            raise TypeError("Can only add query sets to query sets")


class DBElement(ElementBase):
    xmlns = namespaces.db


def make_table_class(model, name, columns, app, table):
    attributes = {
        '_model': model,
        '_app': app,
        '_moyadb': MoyaDB(model, columns, app),
        '_table': table
    }
    cls = type(py2bytes(name),
               (TableClassBase,),
               attributes)
    return cls


class TableClassBase(object):
    """The base class for dynamically created classes that map on to DB abstractions"""

    moya_render_targets = ['html']

    def __init__(self, **kwargs):

        moyadb = self._moyadb
        adapt = moyadb.adapt
        #args = moyadb.defaults.copy()
        for k, v in iteritems(kwargs):
            try:
                setattr(self, k, adapt(k, v))
            except Exception as e:
                raise AdaptValueError("unable to adapt field '{}' to {}".format(k, v), k, v)
        for k, v in moyadb.defaults.items():
            if k not in kwargs:
                setattr(self, k, v() if callable(v) else v)
        #args = {k: v() if callable(v) else v for k, v in moyadb.defaults.items() if not hasattr(self, k)}
        super(TableClassBase, self).__init__()

    @classmethod
    def get_defaults(cls):
        """Get a mapping of defaults for this db class"""
        moyadb = cls._moyadb
        defaults = {}
        for k, v in moyadb.defaults.items():
            if not callable(v):
                defaults[k] = v
        return defaults

    @classmethod
    def _get_column(cls, column_name, default=None):
        return cls._moyadb.moya_columns_map.get(column_name, default)

    @classmethod
    def _get_index(self, archive, context, app, exp_context, index):
        index = index[:]
        node = self
        joins = []
        while index:
            attribute_name = index.pop(0)
            if not index:
                node = getattr(node, attribute_name)
            else:
                if issubclass(node, TableClassBase):
                    col = node._get_column(attribute_name)
                    if col is None:
                        raise KeyError(attribute_name)
                    node, join = col.get_join(node)
                    if join is not None:
                        joins.append(join)
                else:
                    raise ValueError("get index fail")
        if joins:
            exp_context.add_joins(joins)
        return dbobject(node)

    def __moyaconsole__(self, console):
        moyadb = self._moyadb
        table = make_table_header("field name", "value")
        table_body = [(field.name, pilot.context.to_expr(getattr(self, field.name)))
                      for field in moyadb.moya_columns]
        table += table_body
        console.table(table)

    def __iter__(self):
        raise NotImplementedError('not iterable')

    def moya_render(self, archive, context, target, options):
        if target != 'html':
            return repr(self)
        template = self._model.template(context)

        if template is None:
            return repr(self)
        template = self._app.resolve_template(template)
        render_container = RenderContainer.create(self._app, template=template)
        render_container['self'] = self
        if 'with' in options:
            render_container.update(options['with'])
        return render_container.moya_render(archive, context, target, options)

    def __getitem__(self, key):
        """Allow context to return proxy for datetime"""
        try:
            value = getattr(self, key)
        except AttributeError:
            raise KeyError(key)
        else:
            try:
                if isinstance(value, list):
                    value._instance = self
                rel = self._model.relationships.get(key, None)
                # if rel is not None:
                #     value._instance = self
            except Exception as e:
                pass
            if isinstance(value, datetime):
                return ExpressionDateTime.from_datetime(value)
            return value

    def __setitem__(self, key, value):
        try:
            setattr(self, key, dbobject(value))
        except:
            raise ValueError("invalid data type for attribute '{}'".format(key))
        return self

    def keys(self):
        return [name for name in self._moyadb.dbfields]

    def values(self):
        return [getattr(self, name) for name in self._moyadb.dbfields]

    def items(self):
        return [(name, getattr(self, name)) for name in self._moyadb.dbfields]

    def map(self):
        return {name: getattr(self, name) for name in self._moyadb.dbfields}

    def __contains__(self, key):
        return any(key == name for name in self._moyadb.dbfields)

    def __repr__(self):
        """Generated from the `repr` attribute, or uses default of '<model> <id>'."""
        r = self._repr
        try:
            with pilot.context.data_scope(self):
                return "<{}>".format(pilot.context.sub(r))
        except Exception as e:
            log.error("error with repr: %s", e)
            try:
                return "<{} #{}>".format(self._model.get_appid(self.app), self.id)
            except:
                log.exception("error in default repr")
                return "<error in repr>"


class MoyaDB(object):
    def __init__(self, model, columns, app):
        columns = [col(app, model) if callable(col) else col for col in columns]
        self.moya_columns = columns
        self.moya_columns_map = dict((col.name, col) for col in columns)
        sa_columns = sum((list(col.get_sa_columns(model))
                         for col in columns),
                         [])
        self.sa_columns = dict((col.name, col) for col in sa_columns)
        self.dbfields = sorted(col.name for col in columns)
        self.attrib_set = set(self.dbfields)
        self.defaults = {col.name: col.default for col in columns
                         if col.default is not no_default}

    def adapt(self, field, value):
        if field not in self.sa_columns:
            return value
        col = self.sa_columns[field]

        if isinstance(col.type, DateTime):
            if hasattr(value, '__datetime__'):
                value = value.__datetime__()
            elif isinstance(value, (list, tuple)):
                value = ExpressionDateTime(*value)
        else:
            if field in self.moya_columns_map:
                value = self.moya_columns_map[field].adapt(value)
        return value


class ModelProxy(object):
    def __init__(self, model, app):
        super(ModelProxy, self).__init__()
        self._model = model
        self.name = model.name
        self.title = model.title
        self.ref = app.qualify_ref(model.ref)

        self.app = app
        columns = self.columns = []
        for def_app, ext in model._get_extended_definition(app):
            columns.extend(col(app, model) if callable(col) else col for col in ext.columns)

        self.relationships = model.relationships.values()

    def __repr__(self):
        return "<model {} {}>".format(self._model.get_appid(self.app), self._model.name)

    def __moyamodel__(self):
        return self.app, self._model

    def __moyaconsole__(self, console):
        console.text(repr(self), fg="magenta", bold=True)
        console.text("[columns]", fg="green", bold=True)
        table = [[
            Cell("Name", bold=True),
            Cell("Type", bold=True),
            Cell("DB name", bold=True),
        ]]
        for column in self.columns:
            table.append([column.name,
                          column.type,
                          column.dbname])
        console.table(table, header=True)

        console.text("[relationships]", fg="green", bold=True)
        table = [[
            Cell("Name", bold=True),
            Cell("Type", bold=True),
        ]]

        for rel in self.relationships:
            table.append([rel.name,
                          rel.type])
        console.table(table, header=True)


class RelationshipProxy(object):
    def __init__(self, type, name, params, ref_model, widget=None, picker=None):
        for k, v in params.items():
            setattr(self, k, v)
        self.type = type
        self.name = name
        self.ref_model = BoundElement.from_tuple(ref_model)
        if 'widget' not in params:
            self.widget = widget
        self.picker = picker or params.get('picker', None)

    def __repr__(self):
        return "<{} {}>".format(self.type, self.name)


class Doc(DBElement):
    """
    Document a model.

    """
    class Help:
        synopsis = "document a DB model"


class DBModel(DBElement):
    """
    Defines a database [i]model[/i], which maps data stored in a database table on to Moya objects.

    Models are referenced by their [i]libname[/i] in database expressions, the [c]name[/c] attribute is used when creating tables. If you convert a model instance to a string, it will return the value of the [c]repr[/c] attribute, with substitutions made with the object context.

    """

    class Help:
        synopsis = "define a database model"
        example = """
        <model name="Permission" libname="Permission" xmlns="http://moyaproject.com/db"
            repr="Permission '${name}' ${description}">
            <string name="name" required="yes" null="no" blank="no" length="30" unique="yes"/>
            <text name="description" null="no" default=""/>
        </model>

        """

    _name = Attribute("Name of the model (used internally by the db)", required=False, map_to="name")
    _db = Attribute("Database to use (default will use the default database)", map_to="db", default=None)
    _repr = Attribute("Text representation of a model instance (substitution will use the model as a data context)", type="raw", map_to="repr", default=None)
    _abstract = Attribute("Is the model abstract?", type="boolean", default=False, map_to="abstract")
    extends = Attribute("Extend this model", type="elementref", default=None)
    title = Attribute("Descriptive title", type="text", default=None)
    template = Attribute("Optional template to render object", default=None)

    preserve_attributes = ['columns',
                           'column_names',
                           'properties',
                           'object_properties',
                           'constraints',
                           'name',
                           'dbname',
                           'table_map',
                           '_repr'
                           ]

    class Meta:
        tag_name = "model"

    def get_db(self):
        db = (self.archive.database_engines.get(self.dbname, None))
        return db

    def post_build(self, context):
        self.table_map = {}
        self.columns = []
        self.properties = []
        self.object_properties = []
        self.constraints = []
        self.relationships = OrderedDict()
        self._extended_definitions = {}
        self.references = []

        if 'libname' not in self._attrs:
            raise errors.ElementError("a 'libname' attribute is required on this tag",
                                      element=self)

        (name,
         db,
         _repr,
         abstract,
         title) = self.get_parameters(context,
                                      'name',
                                      'db',
                                      'repr',
                                      'abstract',
                                      'title')
        if name is None:
            name = self.libname.lower()

        self.ref = self.document.qualify_element_ref(self.libid)
        if _repr is None:
            _repr = name + " #${id}"
        self.name = name
        self.title = title or name.title()
        self.abstract = abstract
        self.dbname = db or self.archive.default_db_engine
        self._repr = _repr

        self.columns.append(dbcolumns.PKColumn(self.tag_name, "id", primary=True))

        super(DBModel, self).post_build(context)
        self._built_model = False

    def add_column(self, name, column):
        self.columns.append(column)

    def add_property(self, name, prop):
        self.properties.append((name, prop))

    def add_relationship(self, tag_name, name, params, ref_model, widget=None, picker=None):
        rel = RelationshipProxy(tag_name, name, params, ref_model, widget=widget, picker=picker)
        self.relationships[name] = rel

    def add_object_property(self, name, prop):
        self.object_properties.append((name, prop))

    def add_constraint(self, constraint):
        self.constraints.append(constraint)

    def add_reference(self, ref):
        self.references.append(ref)

    def validate(self, app):
        validate_fails = []
        for element in self:
            if hasattr(element, 'validate'):
                try:
                    element.validate(app, self)
                except Exception as e:
                    validate_fails.append((self, app, element, e))
        return validate_fails

    @classmethod
    def validate_all(cls, archive):
        validate_fails = []
        archive.build_libs()
        apps = archive.apps.values()
        for app in apps:
            for model in app.lib.get_elements_by_type((namespaces.db, 'model')):
                try:
                    model._build_model(app)
                except Exception as e:
                    raise
                    if hasattr(e, 'element'):
                        validate_fails.append([model, app, e.element, text_type(e)])
                    else:
                        validate_fails.append([model, app, None, text_type(e)])
        for app in apps:
            for model in app.lib.get_elements_by_type((namespaces.db, 'model')):
                validate_fails.extend(model.validate(app))
        return validate_fails

    @property
    def metadata(self):
        return self.get_db().metadata

    def get_table_and_class(self, app):
        app_name = self.get_table_name(app)
        if app_name not in self.table_map:
            self._build_model(app)
        return self.table_map[app_name]

    def get_table_class(self, app):
        table, table_class = self.get_table_and_class(app)
        return table_class

    def get_table(self, app):
        table, table_class = self.get_table_and_class(app)
        return table

    def get_table_name(self, app):
        for app, _ in self._get_extended_definition(app):
            break
        return "%s_%s" % (app.name.lower(), self.name.lower())

    def make_association_table(self, left_model_table_name, right_model_table_name):
        left = left_model_table_name
        right = right_model_table_name
        name = "%s_to_%s" % (left, right)
        sa_columns = [Column('left_id',
                             Integer,
                             ForeignKey('%s.id' % left, ondelete="CASCADE"),
                             nullable=False
                             #primary_key=True
                             ),
                      Column('right_id',
                             Integer,
                             ForeignKey('%s.id' % right, ondelete="CASCADE"),
                             nullable=False
                             #primary_key=True
                             )
                      ]
        table = Table(name,
                      self.metadata,
                      *sa_columns)

        return table

    def _get_extended_definition(self, app):
        _app = app
        if app.name in self._extended_definitions:
            return self._extended_definitions[app.name]
        model = self
        extends_chain = [(app, self)]
        context = Context(name="_get_extended_definition")
        while 1:
            extend_model_ref = model.extends(context)
            if extend_model_ref is None:
                break
            app, extend_model = self.document.get_app_element(extend_model_ref, app=app)

            if (app, extend_model) in extends_chain:
                raise errors.StartupFailedError('recursive extends in {!r}, {!r} previously included'.format(self, extend_model))

            extends_chain.append((app, extend_model))
            model = extend_model

        definitions = []
        for app, model in reversed(extends_chain):
            definition = ExtendedDefinition(model.columns,
                                            model.properties,
                                            model.object_properties,
                                            model.constraints)
            definitions.append((app, definition))

        self._extended_definitions[_app.name] = definitions
        return definitions

    def _build_model(self, app):
        if self.abstract:
            return
        if self.get_db() is None:
            raise errors.StartupFailedError("can't build model for {}; no database defined".format(self.libid))

        app_name = self.get_table_name(app)
        if app_name in self.table_map:
            return
        table_name = self.get_table_name(app)

        table_names = self.get_db().table_names
        if table_name in table_names:
            raise errors.StartupFailedError("can't build model for {}; duplicate table name '{}'".format(self.libid, table_name))
        table_names.add(table_name)

        app_columns = []
        columns = []
        sa_columns = []

        definitions = self._get_extended_definition(app)

        names = set()
        for definition_app, ext in definitions:
            columns = [(definition_app, col(app, self) if callable(col) else col)
                       for col in ext.columns]
            columns = [(_, c) for _, c in columns if c.name not in names]
            names.update(c.name for _, c in columns)
            app_columns.extend(columns)

        columns = [col for _, col in app_columns]
        sa_columns = sum((list(col.get_sa_columns(self))
                          for col in columns), [])

        for definition_app, ext in definitions:
            sa_columns += ext.constraints

        table = Table(table_name, self.metadata, *sa_columns)

        table_class = make_table_class(self, self.name, columns, app, table)
        table_class._repr = self._repr

        self.table_map[app_name] = (table, table_class)

        properties_map = {}

        for definition_app, col in app_columns:
            for name, prop in col.get_properties(self, table_class):
                if callable(prop):
                    prop = prop(definition_app, self)
                properties_map[name] = prop

        for definition_app, ext in definitions:
            for name, prop in ext.properties:
                if callable(prop):
                    prop = prop(definition_app, self)
                properties_map[name] = prop

        for definition_app, ext in definitions:
            for k, v in ext.object_properties:
                _prop = property(v(definition_app, self) if callable(v) else v)
                setattr(table_class, k, _prop)

        mapper(table_class,
               table,
               properties=properties_map)

        def make_listener(event):
            return lambda mapper, connection, target: self.event_listener(event, app, target)

        event.listen(table_class, 'before_insert', make_listener('db.pre-insert'))
        event.listen(table_class, 'after_insert', make_listener('db.post-insert'))
        event.listen(table_class, 'before_update', make_listener('db.pre-update'))
        event.listen(table_class, 'after_update', make_listener('db.post-update'))
        event.listen(table_class, 'before_delete', make_listener('db.pre-delete'))
        event.listen(table_class, 'after_delete', make_listener('db.post-delete'))

    def create_all(self, archive, engine, app):
        self.metadata.create_all(engine.engine)

    def event_listener(self, event, app, _object):
        if _object is None:
            # TODO: figure out why this occurs
            return
        signal_params = {
            'object': _object,
            'app': app,
            'model': self.libid
        }
        self.archive.fire(pilot.context,
                          event,
                          app,
                          self.libid,
                          signal_params)


class _PropertyCallable(object):
    def __init__(self, element, expression):
        self._element = weakref.ref(element)
        self._expression = expression

    def __call__(self, app, model):
        if self._expression is not None:
            expression = self._expression
            def expression_property(obj):
                return expression.call(pilot.context, obj)
            return expression_property
        else:
            def moya_code_property(obj):
                element = self._element()
                _call = element.archive.get_callable_from_element(element, app=app)
                result = _call(pilot.context, object=obj)
                return result
            return moya_code_property



class Property(DBElement):
    """Add a property to a db object"""

    class Help:
        synopsis = "add a property to a database object"

    class Meta:
        is_call = True

    _name = Attribute("Property name", required=True)
    expression = Attribute("expression using database object", type="function", default=None)

    def document_finalize(self, context):
        params = self.get_parameters(context)
        model = self.get_ancestor((self.xmlns, "model"))
        expression = params.expression if self.has_parameter('expression') else None
        model.add_object_property(params.name, _PropertyCallable(self, expression))


class _ForeignKey(DBElement):
    """Add a [i]foreign key[/i] to a model. A foreign key is a reference to another table.

    A [tag]foreign-key[/tag] tag must appear within a [tag]model[/tag] tag.
    """

    class Help:
        synopsis = "a key to another model"
        example = """
        <!-- foreign key to a User model, called "user", must not be NULL -->
        <foreign-key model="#User" name="user" null="no"/>
        """

    _name = Attribute("Name of the foreign key in the model", required=True)
    model = Attribute("Model element reference", required=True)
    null = Attribute("Allow Null?", type="boolean", default=True)
    blank = Attribute("Allow empty field in Moya admin?", type="boolean")
    default = Attribute("Default value if not set explicitly", default=None)
    primary = Attribute("Primary key?", type="boolean", default=False)
    index = Attribute("Generate a db index?", type="boolean", default=False)
    #ondelete = Attribute("Delete behavior", default="CASCADE", choices=['CASCADE', 'SET NULL'])

    options = Attribute("Objects to consider in admin forms", type="dbexpression", required=False, default=None)
    orderby = Attribute("Default order for admin forms", required=False, default="id")
    label = Attribute("Short description of field purpose")
    help = Attribute("Additional help text for use in object forms")

    backref = Attribute("Back reference", required=False, default=None)
    picker = Attribute("Picker table for admin view", required=False)

    #cascade = Attribute("Cascade behaviour of backref", type="text", default="save-update, merge")

    owner = Attribute("Does this model own the referenced object?", type="boolean", default=False)
    owned = Attribute("Is this model owned by the referenced model?", type="boolean", default=False)

    def document_finalize(self, context):
        params = self.get_parameters_nonlazy(context)
        self.name = name = params.name
        model = self.get_ancestor((self.xmlns, "model"))
        ref_model_ref = params.model

        def get_backref_collection(app, model, name):
            class ListCollection(list):
                def __repr__(self):
                    return "<ListCollection {}>".format(self._instance)

                @property
                def table_class(self):
                    return model.get_table_class(app)

                def __moyaqs__(self, context, dbsession):
                    qs = dbsession.query(self.table_class)
                    qs = qs.filter(getattr(self.table_class, name + '_id') == getattr(self._instance, "id"))
                    return qs

                def _get_query_set(self):
                    # Not a query set, but a list of id works
                    return [getattr(i, 'id') for i in self if hasattr(i, 'id')]
            return ListCollection

        def get_col(app, model):
            try:
                ref_model = self.document.get_app_element(ref_model_ref, app)
            except errors.ElementNotFoundError as e:
                raise errors.ElementError(text_type(e), element=self)

            default = no_default if self.has_parameter('default') else params.default

            ondelete = "CASCADE" if not params.null else "SET NULL"
            cascade = "save-update, merge"
            back_cascade = "save-update, merge"
            if params.owned:
                back_cascade = "all, delete"
            if params.owner:
                cascade = "all, delete"
                ondelete = "CASCADE"

            col = dbcolumns.ForeignKeyColumn(self.tag_name,
                                             name,
                                             ref_model.element,
                                             ref_model.app,
                                             label=params.label,
                                             help=params.help,
                                             default=default,
                                             null=params.null,
                                             blank=params.blank,
                                             primary=params.primary,
                                             index=params.index,
                                             ondelete=ondelete,
                                             options=params.options,
                                             orderby=params.orderby,
                                             backref=params.backref,
                                             picker=params.picker,
                                             cascade=cascade,
                                             back_cascade=back_cascade,
                                             uselist=True,
                                             backref_collection=get_backref_collection(app, model, name))
            ref_model.element.add_reference(model.libid)
            return col

        self.dbname = name + '_id'
        model.add_column(params.name, get_col)


class OneToOne(_ForeignKey):
    """
    A [i]one to one[/i] is a foreign key, that create a single reference to the other model.
    This is reflected in the remote side which has a reference to the linked object, rather than a collection."""

    class Help:
        synopsis = "create a one to one relationship"

    def document_finalize(self, context):
        params = self.get_parameters_nonlazy(context)
        del context
        self.name = name = params.name
        self.model = model = self.get_ancestor((self.xmlns, "model"))
        ref_model_ref = params.model

        def get_col(app, model):
            try:
                ref_model = self.document.get_app_element(ref_model_ref, app)
            except errors.ElementNotFoundError as e:
                raise errors.ElementError(text_type(e), element=self)

            default = no_default if self.has_parameter('default') else params.default

            ondelete = "CASCADE" if not params.null else "SET NULL"
            cascade = "save-update, merge"
            back_cascade = "save-update, merge"
            if params.owned:
                back_cascade = "all, delete-orphan"
            if params.owner:
                cascade = "all, delete"
                ondelete = "CASCADE"

            col = dbcolumns.ForeignKeyColumn(self.tag_name,
                                             name,
                                             ref_model.element,
                                             ref_model.app,
                                             label=params.label,
                                             help=params.help,
                                             default=default,
                                             null=params.null,
                                             blank=params.blank,
                                             primary=params.primary,
                                             index=params.index,
                                             ondelete=ondelete,
                                             options=params.options,
                                             orderby=params.orderby,
                                             backref=params.backref,
                                             picker=params.picker,
                                             cascade=cascade,
                                             back_cascade=back_cascade,
                                             uselist=False)
            ref_model.element.add_reference(model.libid)
            return col

        self.dbname = name + '_id'
        model.add_column(params.name, get_col)


class Relationship(DBElement):
    """Defines a relationship between two tables."""

    class Help:
        synopsis = "define a model relationship that creates a collection"
        example = """<relationship name="links" model="#Link" orderby="-hotness"/>"""

    _name = Attribute("Name of the relationship", required=True)
    model = Attribute("Model", required=True)
    backref = Attribute("Backref")
    orderby = Attribute("Order by", type="commalist", required=False, default=("id",))
    search = Attribute("DB query referencing search field q", type="dbexpression", required=False, default=None)

    def validate(self, app, model):
        try:
            ref_model = self.document.get_app_element(self.ref_model_ref, app)
        except errors.ElementNotFoundError as e:
            raise errors.ElementError(text_type(e), element=self)
        model = self.get_ancestor((self.xmlns, "model"))
        if not isinstance(ref_model.element, DBModel):
            raise DBValidationError("reference '{}' is not a model".format(self.ref_model_ref))
        ref_libid = ref_model.element.libid
        if ref_libid not in model.references:
            msg = "Referenced model '{ref_libid}' should contain a foreignkey to '{libid}'"
            diagnosis = "Add a <foreignkey> to the model referenced by '{ref_libid}', with attribute model=\"{libid}\""
            raise DBValidationError(msg.format(ref_libid=ref_libid, libid=model.libid),
                                    diagnosis=diagnosis.format(ref_libid=ref_libid, libid=model.libid))

    def document_finalize(self, context):
        params = self.get_parameters_nonlazy(context)
        model = self.get_ancestor((self.xmlns, "model"))
        orderby = self.orderby(context)

        def make_relationship(app, model):
            #table = model.get_table(app)
            try:
                app, ref_model = self.document.get_app_element(params.model, app=app)
            except errors.ElementNotFoundError as e:
                raise errors.ElementError(text_type(e), element=self)
            self.ref_model_ref = ref_model.libid
            ref_table, ref_table_class = ref_model.get_table_and_class(app)
            order = lambda: Query._get_order(self.archive, context, ref_table_class, orderby, reverse=False, app=app)

            model.add_relationship(self.tag_name,
                                   params.name,
                                   params._get_param_dict(),
                                   (app, ref_model))

            return relationship(ref_table_class, order_by=order)

        model.add_property(params.name, make_relationship)


def check_collection_target(collection, obj):
    if hasattr(collection, '__check_type__'):
        return collection.__check_type__(obj)
    return True


class ManyToMany(DBElement, DBMixin):

    class Help:
        synopsis = """define a many to may relationship"""
        example = """<many-to-many name="following" backref="followers" model="moya.auth#User"/>"""

    _name = Attribute("Name of the relationship", required=True)
    model = Attribute("Model", required=True)
    backref = Attribute("Back reference", required=False, default=None)
    through = Attribute("Through model", required=False, default=None)
    options = Attribute("Objects to consider in admin forms", type="dbexpression", required=False, default=None)
    search = Attribute("DB query referencing search field q", type="dbexpression", required=False, default=None)
    orderby = Attribute("Default order for admin forms", required=False, default="id")
    keys = Attribute("Foreign keys in association table", required=False, type="commalist", map_to="_keys")
    lazy = Attribute("Specifies how related items should be loaded", required=False)

    label = Attribute("Short description of field purpose")
    backlabel = Attribute("Short description of backref purpose, if used", required=False, default=None)
    help = Attribute("Additional help text for use in object forms")
    picker = Attribute("Admin table to use as a picker control", type="elementref", required=False, default=None)
    backpicker = Attribute("Admin table to use as a picker control for the other side of the relationship", type="elementref", required=False, default=None)

    def validate(self, app, model):
        # if self.has_parameter('through') and not self.has_parameter('keys'):
        #     msg = "'through' table is specified, but no 'keys' given"
        #     diagnosis = """Moya needs to know which foreign keys in '{}' (the through table), join '{}' and '{}'.\n\nSet the 'keys' attribute. For example: keys="user,message" """
        #     raise DBValidationError(msg, diagnosis=diagnosis.format(self.through, model.libid, self.ref_model_ref))
        pass

    def document_finalize(self, context):
        params = self.get_parameters_nonlazy(context)
        model = self.get_ancestor((self.xmlns, "model"))
        self.ref_model_ref = ref_model_ref = params.model
        backref_name = params.backref
        backlabel = params.backlabel
        self.through = through = params.through
        foreign_keys = params._keys

        # if through is not None:
        #     msg = "'through' table is specified, but no 'keys' given"
        #     diagnosis = """Moya needs to know which foreign keys in the through table join the tables. Set the 'keys' attribute. For example keys="user,message" """
        #     raise DBValidationError(msg, diagnosis=diagnosis)

        def get_property(app, model):
            try:
                ref_model = self.document.get_app_element(ref_model_ref, app)
            except errors.ElementNotFoundError as e:
                raise errors.ElementError(text_type(e), element=self)
            ref_table, ref_table_class = ref_model.element.get_table_and_class(ref_model.app)

            table = model.get_table(app)

            _foreign_keys = None
            if through is None:
                assoc_table = model.make_association_table(model.get_table_name(app),
                                                           ref_model.element.get_table_name(ref_model.app))
                primaryjoin = table.c.id == assoc_table.c.left_id
                secondaryjoin = ref_table.c.id == assoc_table.c.right_id
                left_key = "left_id"
                right_key = "right_id"

            else:
                try:
                    _app, assoc_model = self.document.get_app_element(through, app)
                except Exception as e:
                    raise errors.ElementError(text_type(e), element=self)
                assoc_table, assoc_table_class = assoc_model.get_table_and_class(_app)
                try:
                    if not foreign_keys:
                        left_key = model.libname.lower()
                        right_key = ref_model.element.libname.lower()
                    else:
                        left_key, right_key = foreign_keys
                except:
                    primaryjoin = None
                    secondaryjoin = None
                else:
                    left_key += '_id'
                    right_key += '_id'
                    primaryjoin = table.c.id == getattr(assoc_table.c, left_key)
                    secondaryjoin = ref_table.c.id == getattr(assoc_table.c, right_key)

            def get_collection(many_to_many):
                class ListCollection(list):
                    def __repr__(self):
                        return "<ListCollection {}>".format(self._instance)

                    @property
                    def table_class(self):
                        return ref_table_class

                    def __moyadbsubselect__(self, context):
                        dbsession = many_to_many.get_session(context, model.dbname)
                        qs = dbsession.query(getattr(assoc_table.c, right_key))
                        qs = qs.filter(self._instance.id == getattr(assoc_table.c, left_key))
                        return qs

                    def __moyaqs__(self, context, dbsession):
                        qs = dbsession.query(getattr(assoc_table.c, right_key))
                        qs = qs.filter(self._instance.id == getattr(assoc_table.c, left_key))
                        qs = dbsession.query(ref_table_class).filter(ref_table_class.id.in_(qs))
                        return qs

                    def __check_type__(self, obj):
                        return isinstance(obj, ref_table_class)

                return ListCollection

            def get_backref_collection(many_to_many):
                class ListCollection(list):
                    def __repr__(self):
                        return "<ListCollection {}>".format(self._instance)

                    @property
                    def table_class(self):
                        return model.get_table_class(app)

                    def __moyadbsubselect__(self, context):
                        dbsession = many_to_many.get_session(context, model.dbname)
                        qs = dbsession.query(getattr(assoc_table.c, left_key))
                        qs = qs.filter(self._instance.id == getattr(assoc_table.c, right_key))
                        return qs

                    def __moyaqs__(self, context, dbsession):
                        table_class = model.get_table_class(app)
                        qs = dbsession.query(getattr(assoc_table.c, left_key))
                        qs = qs.filter(self._instance.id == getattr(assoc_table.c, right_key))
                        qs = dbsession.query(table_class).filter(table_class.id.in_(qs))
                        return qs

                    def __check_type__(self, obj):
                        table_class = model.get_table_class(app)
                        return isinstance(obj, table_class)

                return ListCollection

            if backref_name:
                rel_backref = backref(backref_name,
                                      collection_class=get_backref_collection(self))
            else:
                rel_backref = None

            rel_property = relationship(ref_table_class,
                                        secondary=assoc_table,
                                        #backref=backref_name,
                                        backref=rel_backref,
                                        primaryjoin=primaryjoin,
                                        secondaryjoin=secondaryjoin,
                                        foreign_keys=_foreign_keys,
                                        collection_class=get_collection(self),
                                        #lazy="dynamic"
                                        )
            model.add_relationship(self.tag_name,
                                   params.name,
                                   params._get_param_dict(),
                                   ref_model)

            if backref_name:
                ref_model.element.add_relationship(self.tag_name,
                                                   backref_name,
                                                   {'backlabel': backlabel or backref_name},
                                                   (app, model),
                                                   picker=params.backpicker)
            return rel_property

        model.add_property(params.name, get_property)


# TODO: Are these tag required?
# class Property(DBElement):
#     name = Attribute("Name for attribute access", type="text", required=True)
#     filter = Attribute("Filter expression", type="dbexpression", required=False, default=None)
#     model = Attribute("Model")

#     def document_finalize(self, context):
#         params = self.get_parameters(context)
#         model = self.get_ancestor((self.xmlns, "model"))

#         def get_property(app):
#             return lambda: 5

#         model.add_property(params.name, get_property)


# class AssociationProxy(DBElement):

#     name = Attribute("Name for attribute access", type="text", required=True)
#     column = Attribute("Column name", type="text", required=True)
#     target_column = Attribute("Target column name", type="text", required=True)
#     model = Attribute("Model")

#     def document_finalize(self, context):
#         params = self.get_parameters(context)
#         model = self.get_ancestor((self.xmlns, "model"))
#         assoc_model_ref = params.model

#         col, target_col = self.get_parameters(context, 'column', 'target_column')

#         def make_association_proxy(app):
#             app, model = self.document.get_element(assoc_model_ref, app)
#             table_class = model.get_table_class(app)
#             return association_proxy(col,
#                                      target_col,
#                                      creator=lambda val: table_class(**{target_col: val}))

#         model.add_object_property(params.name, make_association_proxy)


class FieldElement(DBElement):

    _non_field_attributes = []

    name = Attribute("Name of the element", type="text", required=True)
    null = Attribute("Allow null?", type="boolean", default=False)
    blank = Attribute("Allow blank?", type="boolean", default=True)
    default = Attribute("Default value", default=None)
    primary = Attribute("Use as primary key?", type="boolean")
    index = Attribute("Create index?", type="boolean", default=False)
    unique = Attribute("Impose unique constraint?", type="boolean", default=False)
    label = Attribute("Short description of field purpose")
    help = Attribute("Additional help text for use in object forms")
    formfield = Attribute("Macro to create a form field, used in admin", required=False, default=None)

    def document_finalize(self, context):
        params = self.get_all_parameters(context)
        self.name = params.pop('name').lower()
        del params['default']
        model = self.get_ancestor((self.xmlns, "model"))
        col = self.get_moya_column(context, params)
        self.dbname = col.dbname
        model.add_column(col.name, col)
        #self._default = self.get_default(context)

    def get_default(self, context):
        default = self.default(context) if self.has_parameter('default') else no_default
        #if default is no_default:
        #    return None
        return default

    def get_moya_column(self, context, params):
        params = {k: v for k, v in params.items() if k not in self._non_field_attributes}
        return self.moya_column(self.tag_name,
                                self.name,
                                default=self.get_default(context),
                                **params)


class _Boolean(FieldElement):
    """Defines a [i]boolean[/i] field. Must appear within a <model> tag."""
    moya_column = dbcolumns.BoolColumn
    default = Attribute("Default value", default=None, type="expression")

    class Help:
        synopsis = """a field that is True or False"""
        example = """
        <boolean name="published" default="no" />
        """


class _Float(FieldElement):
    """Defines a [i]floating point[/i] field. Must appear within a <model> tag."""
    moya_column = dbcolumns.FloatColumn
    default = Attribute("Default value", default=None, type="expression")

    class Help:
        synopsis = """a field that stores a floating point number"""
        example = """
            <float name="hotness" default="0"  null="n"/>
        """


class _Decimal(FieldElement):
    """Defines a fixed precision number field in a <model>. Use this field element for currency."""
    moya_column = dbcolumns.DecimalColumn

    precision = Attribute("number of digits", type="integer", default=36)
    scale = Attribute("number of digits after the decimal point", type="integer", default=8)
    default = Attribute("Default value", default=None, type="expression")

    class Help:
        synopsis = """a fix precision number"""
        example = """
            <decimal name="balance" precision="12" scale="2" />
        """


class _Integer(FieldElement):
    """Defines an [i]integer[/i] field. Must appear within a <model> tag."""
    moya_column = dbcolumns.IntegerColumn

    choices = Attribute("A reference to an enum", type="elementref")
    default = Attribute("Default value", default=None, type="expression")

    class Help:
        synopsis = """a field that stores an integer"""
        example = """
        <integer label="Comment count" name="count" default="0" null="no"/>
        """


class _BigInteger(FieldElement):
    """Defines a [i]big integer[/i] field. Must appear within a <model> tag."""
    moya_column = dbcolumns.BigIntegerColumn
    default = Attribute("Default value", default=None, type="expression")

    class Help:
        synopsis = """a field that stores a big integer"""


class _SmallInteger(FieldElement):
    """Defines a [i]small integer[/i] field. Must appear within a <model> tag."""
    moya_column = dbcolumns.SmallIntegerColumn
    default = Attribute("Default value", default=None, type="expression")

    class Help:
        synopsis = """a field that stores a small integer"""


class _String(FieldElement):
    """Defines a [i]string[/i] field. Must appear within a <model> tag."""

    class Help:
        synopsis = """a field that stores a string of characters"""
        example = """
        <string name="first_name" label="First Name" length="30" default="" />
        """

    moya_column = dbcolumns.StringColumn
    length = Attribute("Length of text", required=True, type="integer")
    choices = Attribute("A reference to a choices tag", type="elementref")


class _Upload(FieldElement):
    """An upload field"""

    #_non_field_attributes = ['getpath', 'fs']

    class Help:
        synopsis = """a field to store the path of an uploaded file"""

    moya_column = dbcolumns.UploadColumn
    length = Attribute("Length of text", required=False, type="integer", default=200)
    getfs = Attribute("A macro to get the filesystem to use", required=False, default="elementref")
    getpath = Attribute("Macro that returns a path, will be called with 'upload' and 'form'", type="elementref", required=False)
    geturl = Attribute("Macro that returns a URL for this upload", type="elementref", required=False)

    def get_default(self, context):
        return None


class Token(FieldElement):
    """A string column containing a randomly generated token. Note, that the string is not [i]guaranteed[/i] to be unique.
    If you want a unique token you will have to implement that logic independently."""

    class Help:
        synopsis = """create a randomly generated token in the database"""
        example = """
        <token name="token" length="16" unique="yes" characters="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" />
        """

    moya_column = dbcolumns.StringColumn

    length = Attribute("Maximum length of token", required=True, type="integer")

    size = Attribute("Number of randomly generated characters in the token (defaults to same as length)", required=False, type="integer", default=None)
    characters = Attribute("Choice of characters to use in token (if set, this overrides other character related attributes).", default=None, required=False)
    lowercase = Attribute("Use lower case characters?", type="boolean", default=True, required=False)
    uppercase = Attribute("Use upper case characters?", type="boolean", default=False, required=False)
    digits = Attribute("Use digits?", type="boolean", default=True, required=False)
    punctuation = Attribute("Use punctuation?", type="boolean", default=False, required=False)

    _non_field_attributes = ['size', 'characters', 'lowercase', 'uppercase', 'digits', 'punctuation']

    def get_default(self, context):
        size = self.size(context)
        length = self.length(context)
        size = min(length, size or length)
        choices = self.characters(context) or ''

        (lowercase,
         uppercase,
         digits,
         punctuation) = self.get_parameters(context,
                                            "lowercase",
                                            "uppercase",
                                            "digits",
                                            "punctuation")
        if not choices:
            if lowercase:
                choices += string.lowercase
            if uppercase:
                choices += string.uppercase
            if digits:
                choices += string.digits
            if punctuation:
                choices += string.punctuation
        if not choices:
            raise errors.ElementError("No choice of characters for random token",
                                      element=self,
                                      diagnosis="Set the 'characters' attribute to a non-empty string, or one of the other attributes to set the choice of characters.")
        return lambda: ''.join(choice(choices) for _ in xrange(size))


class UUID(FieldElement):
    """
    Create a UUID field (http://en.wikipedia.org/wiki/Universally_unique_identifier).

    """

    class Help:
        synopsis = """create a UUID in the database"""
        example = """
        <uuid name="uuid" version="3" namespace="dns" name="moyaproject.com" />
        """

    moya_column = dbcolumns.StringColumn

    length = Attribute("Maximum length of UUID (should be >= 36)", required=False, default=36, type="integer")

    version = Attribute("Type of UUID", choices=['1', '3', '4', '5'], default="1")
    nstype = Attribute("Namespace (if using variant 3 or 5)", choices=["dns", 'url', 'oid', 'x500'], default="url")
    nsname = Attribute("Name in namespace (if using variant 3 or 5)", default="http://moyaproject.org")

    _non_field_attributes = ['version', 'nstype', 'nsname']

    _namespace_map = {
        "dns": uuid.NAMESPACE_DNS,
        "url": uuid.NAMESPACE_URL,
        "oid": uuid.NAMESPACE_OID,
        "x500": uuid.NAMESPACE_X500
    }

    def get_default(self, context):
        version, nstype, nsname = self.get_parameters(context,
                                                      'version',
                                                      'nstype',
                                                      'nsname')

        def getter():
            namespace = self._namespace_map[nstype]
            if version == "1":
                uid = uuid.uuid1()
            elif version == "3":
                uid = uuid.uuid3(namespace, nsname)
            elif version == "4":
                uid = uuid.uuid4()
            elif version == "5":
                uid = uuid.uuid5(namespace, nsname)
            uid_value = text_type(uid)
            return uid_value

        return getter


class Timezone(FieldElement):
    """Defines a [i]timezone[/i] field."""

    class Help:
        synopsis = """a field that stores a timezone"""

    moya_column = dbcolumns.TimezoneColumn
    length = Attribute("Length of text", required=True, type="integer", default=50)
    choices = Attribute("A sequence of possible choices", type="expression", default=timezone.get_common_timezones_groups())


class _Text(FieldElement):
    """Defines a [i]text[i] field."""

    markup = Attribute("Format of text field, used by Moya Admin to pick an editor", required=False, default="text")

    class Help:
        synopsis = """a field that stores arbitrary length text"""
        example = """
        <text name="description" null="no" default=""/>
        """

    moya_column = dbcolumns.TextColumn


class _Datetime(FieldElement):
    """Defines a [i]datetime[/i] field."""

    class Help:
        synopsis = """a field that stores a date and time"""
        example = """
        <datetime name="last_login" label="Date of last login" null="yes" />
        """

    moya_column = dbcolumns.DatetimeColumn
    auto = Attribute("Set to current time when created", type="boolean", default=False)

    def get_default(self, context):
        if self.auto(context):
            return lambda: ExpressionDateTime.utcnow()


class _Date(FieldElement):
    """Defines a [i]date[/i] field."""

    class Help:
        synopsis = """a field that stores a date"""

    moya_column = dbcolumns.DateColumn
    auto = Attribute("Set to current time when created", type="boolean", default=False)

    def get_default(self, context):
        if self.auto(context):
            return lambda: ExpressionDateTime.utcnow().date


# TODO: document
class StringMap(FieldElement):
    moya_column = dbcolumns.StringMapColumn

    class Help:
        synopsis = """a field that stores a mapping of keys and strings"""

    def get_default(self, context):
        return None


class _GenericKey(FieldElement):
    """
    Create a [i]generic[/i] key. A generic key is [tag db]foreign-key[/tag], but can link to any database object.

    """
    moya_column = dbcolumns.GenericKeyColumn

    class Help:
        synopsis = """a generic foreign key"""

    def get_default(self, context):
        return None


class DBDataSetter(DataSetter, DBMixin):
    xmlns = namespaces.db

    class Help:
        undocumented = True

    def _qs(self, context, dbsession, value):
        if hasattr(value, '__moyaqs__'):
            return value.__moyaqs__(context, dbsession)
        if hasattr(value, '_get_query_set'):
            value = value._get_query_set()
        return value


class Create(DBDataSetter):
    """Create new object in the database."""

    class Help:
        synopsis = "create an object in the database"
        example = """

            <db:create model="#User"
                let:username="username"
                let:email="email"
                let:first_name="first_name"
                let:last_name="last_name"
                let:password="password"
                dst="newuser" />

        """

    model = Attribute("Model element reference", type="text", required=True)
    db = Attribute("Database name", default="_default")
    dst = Attribute("Destination", default=None)
    obj = Attribute("Object with initial values", required=False, default=None, type="index")
    _from = Attribute("Application", type="application", default=None)

    @wrap_db_errors
    def logic(self, context):
        params = self.get_parameters(context)
        element_app = self.get_app(context)
        app, model = self.get_model(context, params.model, app=element_app)
        dbsession = self.get_session(context, params.db)
        table_class = model.get_table_class(app)

        obj = params.obj or {}
        fields = {k: dbobject(v) for k, v in obj.items()}
        fields.update({k: dbobject(v) for k, v in self.get_let_map(context, check_missing=True).items()})
        fields.pop('id', None)

        with context.data_scope(fields):
            yield DeferNodeContents(self)

        try:
            value = table_class(**fields)
        except AdaptValueError as e:
            self.throw('db.create-fail',
                        "unable to set field '{}' to {}".format(e.k, context.to_expr(e.v)),
                        fields,
                        diagnosis="Check the field supports the data type you are setting")
        except Exception as e:
            self.throw('db.create-fail',
                        "unable to create a new {} object ({})".format(model, e),
                        fields,
                        diagnosis="Check the field supports the data type you are setting")

        if params.dst is not None:
            self.set_context(context, params.dst, value)

        signal_params = {'object': value, 'model': model.libid, 'app': app}
        self.archive.fire(context,
                          'db.pre-create',
                          element_app,
                          model.libid,
                          signal_params)

        try:
            with dbsession.manage(self):
                dbsession.add(value)
        except IntegrityError as e:
            value = None
            self.throw('db.integrityerror', text_type(e))
        except OperationalError as e:
            value = None
            self.throw('db.operationalerror', text_type(e))

        self.archive.fire(context,
                          'db.post-create',
                          element_app,
                          model.libid,
                          signal_params)


class GetOrCreate(DBDataSetter):
    """
    Get an object from the db if it exists, create it if it doesn't.

    If the object is created, the code in the enclosed block is executed.

    """

    class Help:
        synopsis = """get an object from the database, or create it if it doesn't exist."""
        example = """
            <db:get-or-create model="#Permission" let:name="'admin'"
                let:description="'User may perform administration tasks'">
                <echo>New permission was created.
            </db:get-or-create>
        """

    model = Attribute("Model element reference", type="text", required=True)
    db = Attribute("Database name", default="_default")
    dst = Attribute("Destination", default=None)
    created = Attribute("Destination to store created flag", type="index", default=None)
    initial = Attribute("Object with initial values", required=False, default=None, type="expression")
    _from = Attribute("Application", type="application", default=None)
    filter = Attribute("Filter expression", type="dbexpression", required=False, default=None)
    forupdate = Attribute("Issue a select FOR UPDATE?", type="boolean", required=False, default=False)

    @wrap_db_errors
    def logic(self, context):
        params = self.get_parameters(context)
        element_app = self.get_app(context)
        app, model = self.get_model(context, params.model, app=element_app)

        if params.filter:
            filter, exp_context = params.filter.eval2(self.archive, context, app)
        else:
            filter = None

        dbsession = self.get_session(context, params.db)
        table_class = model.get_table_class(app)

        created = False
        dst = params.dst
        let_map = self.get_let_map(context, check_missing=True)
        query = Get._get_attributes_query(self, context, table_class, let_map)
        qs = dbsession.query(table_class).filter(*query)
        if params.forupdate:
            qs = qs.with_for_update()

        if filter is not None:
            qs = qs.filter(filter)
            qs = exp_context.process_qs(qs)

        value = qs.first()

        if value is None:
            created = True
            obj = params.initial or {}
            fields = {k: dbobject(v) for k, v in obj.items() if k != 'id'}
            fields.update({k: dbobject(v) for k, v in let_map.items()})

            value = table_class(**fields)

            signal_params = {'object': value,
                             'model': model.libid,
                             'app': app}

            self.archive.fire(context,
                              'db.pre-create',
                              element_app,
                              model.libid,
                              signal_params)

            try:
                with dbsession.manage(self):
                    dbsession.add(value)
            except IntegrityError as e:
                self.throw('db.integrity-error', text_type(e))
            except OperationalError as e:
                self.throw('db.operational-error', text_type(e))

            self.archive.fire(context,
                              'db.post-create',
                              element_app,
                              model.libid,
                              signal_params)

        dst = self.set_context(context, dst, value)
        if params.created:
            context[params.created] = created

        if created:
            yield logic.DeferNodeContents(self)


# TODO: is this used?
# class Insert(DBDataSetter):

#     model = Attribute("Model", type="text", required=True)
#     db = Attribute("Database", type="text", default="_default")
#     dst = Attribute("Destination", type="reference", default=None)
#     src = Attribute("Source", type="reference")

#     @wrap_db_errors
#     def logic(self, context):
#         params = self.get_parameters(context)
#         obj = context[params.src]
#         app = context['app']
#         model = self.get_model(context, params.model)
#         dbsession = self.get_session(context, params.db)
#         value = model.get_table_class(app)(**obj)
#         dst = self.set_context(context, params.dst, value)
#         context[dst] = value
#         dbsession.add(value)


class DBContextElement(ContextElementBase, DBMixin):
    xmlns = namespaces.db

    class Help:
        undocumented = True


class BulkCreate(ContextElementBase, DBMixin):
    """Create database object in bulk via JSON. Useful for quickly adding fixture data."""

    class Help:
        synopsis = """bulk create database objects"""

    xmlns = namespaces.db

    model = Attribute("Model", type="text", required=True)
    db = Attribute("Database", type="text", default="_default")
    dst = Attribute("Destination", type="reference", default=None)
    _from = Attribute("Application", type="expression", default=None)

    @wrap_db_errors
    def logic(self, context):

        params = self.get_parameters(context)
        json = loads(self.text)
        app, model = self.get_model(context, params.model, app=self.get_app(context))
        dbsession = self.get_session(context, params.db)

        table_class = model.get_table_class(app)
        with dbsession.manage(self):
            for item in json:
                dbsession.add(table_class(**item))


class DeleteAll(ContextElementBase, DBMixin):
    """Delete every object from a table"""

    class Help:
        synopsis = """delete all objects in a table"""
        example = """
        <db:delete-all model="#Post"/>
        """

    xmlns = namespaces.db

    model = Attribute("Model", required=True)
    db = Attribute("Database", default="_default")

    @wrap_db_errors
    def logic(self, context):
        _model, db = self.get_parameters(context, 'model', 'db')
        app, model = self.get_model(context, _model)
        session = self.get_session(context, db)
        session.query(model.get_table_class(app)).delete()


class Delete(ContextElementBase, DBMixin):
    """Delete an object from the database."""

    class Help:
        synopsis = "delete from the database"
        example = """
        <db:get model="#Post" let:name="first_post" dst="post"/>
        <db:delete src="post"/>
        """

    xmlns = namespaces.db

    db = Attribute("Database", default="_default")
    src = Attribute("Object or queryset to delete", type="expression", required=True, missing=False)

    @wrap_db_errors
    def logic(self, context):
        db, src = self.get_parameters(context, 'db', 'src')
        dbsession = self.get_session(context, db)

        try:
            with dbsession.manage(self):
                if isinstance(src, MoyaQuerySet):
                    for item in src:
                        dbsession.delete(item)
                else:
                    dbsession.delete(src)
        except UnmappedInstanceError as e:
            self.throw('db.delete.fail',
                       'Object {} is not stored in the db and could not be deleted'.format(context.to_expr(src)))


class Get(DBDataSetter):
    """
    Get an object from the database.

    This tag will return a dagabase object if it exists, otherwise `None`. Additionally, if the object exists, the enclosed block will be executed.
    """

    class Help:
        synopsis = """get an object in the database."""
        example = """
            <db:get model="#Topic" let:slug="url.topic" dst="topic"/>
        """

    class Meta:
        one_of = [('model', 'modelobj')]

    xmlns = namespaces.db
    default = None

    model = Attribute("Model element reference", required=False)
    modelobj = Attribute("Model object", type="expression", default=None)

    db = Attribute("Database to use", default="_default")
    orderby = Attribute("Order by", type="commalist", required=False, default=None)
    dst = Attribute("Destination", type="reference", default=None)
    _from = Attribute("Application", type="application", default=None)
    filter = Attribute("Filter expression", type="dbexpression", required=False, default=None)
    src = Attribute("query set to restrict search", type="expression", required=False, default=None)
    forupdate = Attribute("Issue a select FOR UPDATE?", type="boolean", required=False, default=False)

    @classmethod
    def _get_attributes_query(cls, element, context, table_class, let_map):
        q = []
        append = q.append
        for k, v in let_map.items():
            try:
                append(getattr(table_class, k) == dbobject(v))
            except:
                element.throw("db.get.invalid-comparison",
                              "field {} can not be compared with value {}".format(context.to_expr(k), context.to_expr(v)),
                              diagnosis="check the type of the value matches the column in the database model")
        return q

    @wrap_db_errors
    def logic(self, context):
        params = self.get_parameters(context)
        app = self.get_app(context)

        if params.modelobj is None:
            app, model = self.get_model(context, params.model, app=app)
        else:
            model = params.modelobj

        if params.filter:
            filter, exp_context = params.filter.eval2(self.archive, context, app)
        else:
            filter = None

        dbsession = self.get_session(context, params.db)

        let_map = self.get_let_map(context).items()
        for k, v in let_map:
            if is_missing(v):
                diagnosis = '''\
Moya can't except a missing value here. If you intended to use this value (i.e. it wasn't a typo), you should convert it to a non-missing value.

For example **let:{k}="name or 'anonymous'"**
'''
                raise errors.ElementError("parameter '{k}' must not be missing (it is {v!r})".format(k=k, v=v),
                                          diagnosis=diagnosis.format(k=k, v=v))

        query = {k: dbobject(v) for k, v in let_map}

        table_class = model.get_table_class(app)

        for k in query:
            if not hasattr(table_class, k):
                self.throw("db.unknown-field",
                           "the value '{}' is not a valid attribute for this model".format(k))

        query = self._get_attributes_query(self, context, table_class, query)

        if params.src:
            src = params.src
            qs = self._qs(context, dbsession, src)
            qs = qs.filter(*query)
        else:
            qs = dbsession.query(table_class).filter(*query)

        if params.forupdate:
            qs = qs.with_for_update()

        if filter is not None:
            qs = qs.filter(filter)
            qs = exp_context.process_qs(qs)

        if params.orderby:
            qs = Query._make_order(self, qs, self.archive, context, table_class, params.orderby, app=app)

        value = self.get_value(context, qs)
        self.check_value(context, value)

        self.set_context(context, self.dst(context), value)

        if value:
            yield logic.DeferNodeContents(self)

    def get_value(self, context, qs):
        return qs.first()

    def check_value(self, context, value):
        pass


class GetOne(Get):
    """
    Like [tag db]get[/tag], but will throw a [c]db.multiple-results[/c] if there are more than one result, or [c]db.no-result[/c] if there are no results.

    """

    class Help:
        synopsis = "get precisely one matching object"
        example = None

    def get_value(self, context, qs):
        try:
            result = qs.one()
        except NoResultFound:
            self.throw('db.no-result',
                       "there was no matching result")
        except MultipleResultsFound:
            self.throw("db.multiple-results",
                       "multiple objects were returned")
        else:
            return result


class IfExists(ContextElementBase, DBMixin):
    """Execute the enclosed block if a object exists in the db."""

    class Help:
        synopsis = """execute a block if an object exists in the database"""
        example = """
            <db:if-exists model="#Link" let:topic="topic" let:slug="slug" >
                <forms:error>Slug exists, please edit the title</forms:error>
                <break/>
            </db:if-exists>
        """

    xmlns = namespaces.db
    model = Attribute("Model", required=False)
    modelobj = Attribute("Model object", type="expression", default=None)
    filter = Attribute("Filter expression", type="dbexpression", required=False, default=None)

    db = Attribute("Database", default="_default")
    _from = Attribute("Application", type="application", default=None)

    @wrap_db_errors
    def logic(self, context):
        params = self.get_parameters(context)
        app = self.get_app(context)
        if params.modelobj is None:
            app, model = self.get_model(context, params.model, app)
        else:
            model = params.modelobj
        dbsession = self.get_session(context, params.db)

        query = {k: dbobject(v) for k, v in self.get_let_map(context).items()}

        table_class = model.get_table_class(app)
        #query = ((getattr(table_class, k) == v) for k, v in query.items())

        query = Get._get_attributes_query(self, context, table_class, query)

        qs = dbsession.query(table_class).filter(*query)

        if params.filter:
            filter, exp_context = params.filter.eval2(self.archive, context, app)
            qs = qs.filter(filter)

        value = qs.first()

        if self._test(value):
            yield DeferNodeContents(self)
            yield SkipNext((namespaces.default, "else"), (namespaces.default, "elif"))

    def _test(self, value):
        return value is not None


class IfNotExists(IfExists):
    """Executes the enclosed block if an object does not exists in the db."""

    class Help:
        synopsis = "executes a block of code if an object does not exist in the db"

    def _test(self, value):
        return value is None


class GetRequired(Get):
    """Gets an object from the db. If the object is not present in the db then return a 404 (not found) response. This is useful when page content corresponds to a single object in the database."""
    xmlns = namespaces.db
    default = None

    status = Attribute("Status code", type="httpstatus", required=False, default=404)

    class Help:
        synopsis = """get an object from the database, or return a 404 if it doesn't exist"""
        example = """
        <db:get-required model="#Post" dst="post" let:slug="url.slug" />
        """

    def check_value(self, context, value):
        if value is None:
            status = self.status(context)
            raise logic.EndLogic(http.RespondWith(status))


class GetExist(Get):
    """Gets an object from the db, or throws a [c]moya.db.does-not-exist[/c] exception if it doesn't exist"""

    xmlns = namespaces.db
    default = None

    def check_value(self, context, value):
        if value is None:
            self.throw('moya.db.does-not-exist', 'No such object in the database')


def query_flatten(qs):
    for obj in qs:
        if hasattr(obj, '__iter__'):
            for item in obj:
                yield item
        else:
            yield obj


class GetColumn(DBDataSetter):
    """Get a specific column from the database. This is required if you don't know the column reference ahead of time, i.e. when you want to generate a query dynamically from a table. Moya Admin uses this tag, but it unlikely to be useful for general applications."""

    class Help:
        synopsis = """get a column from a model"""
        example = """
       <db:getcolumn model="${table.params.model}"
            name="id" from="${.url.appname}" dst="id_column" />
        """

    xmlns = namespaces.db

    _from = Attribute("Model app", type="application", required=False, default=None)
    model = Attribute("Model reference", required=False, default=None)
    modelobj = Attribute("Model object", type="expression", required=False, default=None)
    name = Attribute("Column name", required=True)

    def logic(self, context):
        params = self.get_parameters(context)
        app = self.get_app(context)
        if params.model is not None:
            model_app, model = self.get_element(params.model, app=app)
        else:
            model = params.modelobj
            model_app = app
        if hasattr(model, '__moyamodel__'):
            model_app, model = model.__moyamodel__()
        try:
            table_class = model.get_table_class(model_app)
        except AttributeError:
            self.throw('bad-value.not-a-model',
                       "value {} does not appear to be a model".format(context.to_expr(model)))
        try:
            column = getattr(table_class, params.name)
        except AttributeError:
            self.throw('bad-value.missing-column',
                       "model doesn't contain a column called '{}'".format(params.name))
        self.set_context(context, params.dst, column)


class Inspect(DBDataSetter):
    """Inspect a DB model, so you can view column information. Used by Moya Admin."""

    class Help:
        synopsis = """get model information"""
        example = """
            <db:inspect model="${table.params.model}" from="${.url.appname}" dst="model" />
        """

    xmlns = namespaces.db

    _from = Attribute("Model app", type="application", required=False, default=None)
    model = Attribute("Model reference", required=True)

    def logic(self, context):
        params = self.get_parameters(context)
        app = self.get_app(context)
        model_app, model = self.get_element(params.model, app=app)
        table_class = model.get_table_class(model_app)
        model_proxy = ModelProxy(model, model_app)
        self.set_context(context, params.dst, model_proxy)


class GetDefaults(DataSetter):
    xmlns = namespaces.db

    _from = Attribute("Model app", type="application", required=False, default=None)
    model = Attribute("Model reference", required=True)

    def get_value(self, context):
        params = self.get_parameters(context)
        app = self.get_app(context)
        model_app, model = self.get_element(params.model, app=app)
        table_class = model.get_table_class(model_app)
        return table_class.get_defaults()


class NewQuery(DBDataSetter):
    """Create a query object dynamically."""

    class Help:
        synopsis = """dynamically create a database query"""
        example = """
        <db:new-query model="relationship.ref_model" from="${relationship.ref_model.app.name}" dst="related" />
        """

    xmlns = namespaces.db

    db = Attribute("Database", default="_default")
    model = Attribute("Model", type="expression", required=True)
    _from = Attribute("Model app", type="application", required=False, default=None)

    def logic(self, context):
        params = self.get_parameters(context)
        dbsession = self.get_session(context, params.db)
        app = self.get_app(context)

        model = params.model
        if hasattr(model, '__moyamodel__'):
            app, model = model.__moyamodel__()

        table_class = model.get_table_class(app)
        qs = dbsession.query(table_class)
        qs = MoyaQuerySet(qs, table_class, dbsession)
        self.set_context(context, params.dst, qs)


class Sort(DBDataSetter):
    """Sort a Query Set"""

    class Help:
        synopsis = """sort a query set"""

    xmlns = namespaces.db
    dst = Attribute("Destination", type="reference", default=None)
    _from = Attribute("Model app", type="application", required=False, default=None)
    src = Attribute("Source query, if further query operations are required", type="reference", default=None, metavar="QUERYSET")
    orderby = Attribute("Order by", type="commalist", required=True)
    reverse = Attribute("Reverse order?", type="expression", required=False, default=False)

    def logic(self, context):
        params = self.get_parameters(context)

        app = self.get_app(context)

        qs = context[params.src]
        dbsession = qs.dbsession
        table_class = qs.table_class
        if hasattr(qs, '_get_query_set'):
            qs = qs._get_query_set()

        qs = Query._make_order(qs,
                               self.archive,
                               context,
                               None,
                               params.orderby,
                               params.reverse,
                               app=app)

        dst = params.dst or params.src
        qs = MoyaQuerySet(qs, table_class, dbsession)
        self.set_context(context, dst, qs)


class SortMap(DBDataSetter):
    """
    Sort a query set in one of a number of different ways.

    This is typically used to sort a table of results based on a value in the query set.

    """

    class Help:
        synopsis = """sort a query set dynamically"""
        example = """
        <db:sort-map src="characters" sort=".request.GET.sort" reverse=".request.GET.order=='desc'">
            <str dst="name">#Character.name</str>
            <str dst="species">#Character.species</str>
            <str dst="age">#Character.age</str>
        </db:sort-map>
        """

    xmlns = namespaces.db

    dst = Attribute("Destination", type="reference", default=None)
    _from = Attribute("Model app", type="application", required=False, default=None)
    src = Attribute("Query to sort", type="reference", default=None, metavar="QUERYSET", missing=False, required=True)
    sort = Attribute("Sort value?", type="expression", required=False, evaldefault=True, default=".request.GET.sort")
    reverse = Attribute("Reverse order?", type="expression", required=False, default=".request.GET.order=='desc'", evaldefault=True)
    columns = Attribute("Sort columns", type="expression", required=False)

    def logic(self, context):
        params = self.get_parameters(context)
        app = self.get_app(context)

        qs = context[params.src]
        if is_missing(qs):
            raise errors.ElementError("attribute 'src' must not be missing (it is {!r})".format(qs),
                                      element=self)

        dbsession = qs.dbsession
        table_class = qs.table_class
        if hasattr(qs, '_get_query_set'):
            qs = qs._get_query_set()

        sort_map = params.columns or {}
        if not hasattr(sort_map, 'items'):
            self.throw("bad-value.columns",
                       "Columns attribute should be a dict or other mapping")
        with context.data_scope(sort_map):
            yield DeferNodeContents(self)

        orderby = sort_map.get(params.sort, None)

        if orderby is not None:
            qs = Query._make_order(self, qs,
                                   self.archive,
                                   context,
                                   None,
                                   [orderby],
                                   params.reverse,
                                   app=app)

            dst = params.dst or params.src
            qs = MoyaQuerySet(qs, table_class, dbsession)
            self.set_context(context, dst, qs)


class Query(DBDataSetter):
    """Query the database. Will return a query set object that may be iterated over by default, unless [c]'collect'[/c] is specified."""

    class Help:
        synopsis = """query the database"""
        example = """
        <!-- examples taken from Moya apps -->

        <!-- Get a month worth of posts -->
        <db:query model="#Post" dst="posts" orderby="-published_date"
            filter="#Post.published_date gte start and #Post.published_date lt start.next_month"/>

        <!-- delete a user session -->
        <db:query model="#Session" let:session_key=".request.cookies.authsession" action="delete"/>

        <!-- get promoted topics in Moya Social Links -->
        <db:query model="#Topic" filter="#Topic.promoted == yes" orderby="#Topic.title" dst="promoted_topics"/>

    """

    class Meta:
        one_of = [('model', 'columns', 'src')]

    xmlns = namespaces.db

    model = Attribute("Model", required=False, default=None, metavar="ELEMENTREF")
    _from = Attribute("Model app", type="application", required=False, default=None)
    db = Attribute("Database", default="_default")
    src = Attribute("Source query, if further query operations are required", type="expression", default=None, metavar="QUERYSET", missing=False)
    dst = Attribute("Destination", type="reference", default=None)
    filter = Attribute("Filter expression", type="dbexpression", required=False, default=None)
    orderby = Attribute("Order by", type="commalist", required=False, default=None)
    reverse = Attribute("Reverse order?", type="expression", required=False, default=False)
    distinct = Attribute("Make query distinct (remove duplicates from results)?", type="boolean", default=False)
    columns = Attribute("Columns to return, if model is not specified", type="dbexpression", required=False, default=None)
    flat = Attribute("Flatten results in to a list?", type="boolean", required=False, default=False)
    collect = Attribute("Collect results?", required=False, choices=['list', 'set', 'dict', 'dict_sequence'])
    collectkey = Attribute("Collect key if collect is True", required=False, default=None)
    start = Attribute("Start index", type="expression", required=False, default=None)
    maxresults = Attribute("Maximum number of items to return", type="expression", default=None, required=False)
    action = Attribute("Action to perform on query", default=None, required=False, choices=['delete', 'count', 'exists'])
    join = Attribute("Join expressions", type="dbexpression", required=False, default=None)
    groupby = Attribute("Group by column(s)", type="commalist", required=False, default=None)
    forupdate = Attribute("Issue a select FOR UPDATE?", type="boolean", required=False, default=False)

    @classmethod
    def _get_order(cls, archive, context, table_class, orderby, reverse=False, app=None):
        order = []
        for field in orderby:
            if not field:
                continue
            descending = field.startswith('-')
            if descending:
                field = field[1:]

            if '#' in field:
                sort_col, exp_context = DBExpression(field).eval2(archive, context, app)
                if reverse or descending:
                    sort_col = desc(sort_col)
                order.append(sort_col)
            else:
                if not table_class:
                    raise ValueError("Model required for order")
                else:
                    sort_col = getattr(table_class, field)
                    if reverse or descending:
                        sort_col = sort_col.desc()
                    order.append(sort_col)
        return order

    @classmethod
    def _make_order(cls, element, qs, archive, context, table_class, orderby, reverse=False, app=None):
        order = []
        for field in orderby:
            if not field:
                continue
            descending = field.startswith('-')
            if descending:
                field = field[1:]

            if '#' in field:
                sort_col, exp_context = DBExpression(field).eval2(archive, context, app)
                if qs is not None:
                    qs = exp_context.process_qs(qs)
                if reverse or descending:
                    sort_col = desc(sort_col)
                order.append(sort_col)
            else:
                if not table_class:
                    element.throw('db.model-required',
                                  'Model required for order',
                                  diagnosis='Specify the model attribute, or use a field reference in order by (e.g. order="#Model.field")')
                else:
                    sort_col = getattr(table_class, field, None)
                    if sort_col is None:
                        raise errors.ElementError("sort field '{}' was not recognized".format(field),
                                                  diagnosis='check the "orderby" field for typos')
                    if reverse or descending:
                        sort_col = sort_col.desc()
                    order.append(sort_col)
        if order:
            # First cancel any existing order
            qs = qs.order_by(False).order_by(*order)
        return qs

    @wrap_db_errors
    def logic(self, context):
        params = self.get_parameters(context)
        dbsession = self.get_session(context, params.db)
        app = self.get_app(context)

        if params.filter:
            filter, exp_context = params.filter.eval2(self.archive, context, app)
        else:
            filter = None

        table_class = None

        if params.src is not None:
            qs = self._qs(context, dbsession, params.src)
            table_class = getattr(dbobject(params.src), 'table_class', None)
            if table_class is None:
                raise errors.ElementError('src attribute must be a database object, not {}'.format(context.to_expr(params.src)), element=self)
        else:
            if params.model:
                try:
                    model_app, model = self.get_app_element(params.model, app=app)
                except errors.ElementNotFoundError as e:
                    raise errors.ElementError(text_type(e), element=self)
                table_class = model.get_table_class(model_app)
                qs = dbsession.query(table_class)
            else:
                qs = dbsession.query()

        if params.forupdate:
            qs = qs.with_for_update()

        if params.columns is not None:
            columns = params.columns.eval(self.archive, context, app=app)
            if not isinstance(columns, list):
                columns = [columns]
            try:
                qs = dbsession.query(*columns)
            except:
                raise self.throw('db.bad-columns',
                                 "'columns' attribute must refer to columns only")

        if params.join is not None:
            joins = params.join.eval(self.archive, context)
            if not isinstance(joins, list):
                joins = [joins]
            try:
                for j in joins:
                    if isinstance(j, (tuple, list)):
                        qs = qs.join(*j)
                    else:
                        qs = qs.join(j)
                qs = qs.join(*joins)
            except Exception as e:
                self.throw('db.bad-join',
                           text_type(e))

        if params.groupby is not None:
            group_by = [DBExpression(g).eval(self.archive, context, app) for g in params.groupby]
            qs = qs.group_by(*group_by)

        if filter is not None:
            try:
                qs = qs.filter(filter)
            except Exception as e:
                self.throw('db.filter-failed',
                           'unable to apply filter to queryset',
                           diagnosis="Moya's db engine reported the following:\n\n**{}**".format(e))
            qs = exp_context.process_qs(qs)

        if table_class is not None:
            query_data = {k: dbobject(v) for k, v in self.get_let_map(context).items()}
            for k, v in query_data.items():
                if is_missing(v):
                    self.throw('bad-value.missing',
                               "filter attribute '{{{}}}{}' should not be missing (it is {!r})".format(namespaces.let, k, v),
                               diagnosis="Let key '{}' refers to a missing value, which is invalid for this tag. If you want to query a null value in the database, you could convert to None with the **none:** modifier.".format(k))
                try:
                    qs = qs.filter(getattr(table_class, k) == v)
                except:
                    self.throw('bad-value.invalid-filter',
                               "Can't filter {} on column '{}'".format(context.to_expr(v), k),
                               diagnosis="Check the field type is compatible with the value you wish to filter on.")
        else:
            if self.get_let_map(context):
                self.throw('bad-value.model-required',
                           "Moya can't use LET attributes without a model",
                           diagnosis="Specfiy the 'model' or use the 'filter' attribute")

        if params.orderby:
            qs = Query._make_order(self,
                                   qs,
                                   self.archive,
                                   context,
                                   table_class,
                                   params.orderby,
                                   params.reverse,
                                   app=app)

        if params.distinct:
            qs = qs.distinct()

        if params.start or params.maxresults:
            start = params.start or 0
            qs = qs.slice(start, start + params.maxresults)

        if params.action == "delete":
            self.set_context(context, params.dst, qs.delete())
            return

        if params.action == "count":
            self.set_context(context, params.dst, qs.count())
            return

        if params.action == "exists":
            self.set_context(context, params.dst, qs.first() is not None)
            return

        if params.flat:
            qs = list(query_flatten(qs))

        elif params.collect:
            if params.collect == "list":
                collectkey = params.collectkey
                if collectkey:
                    qs = [getattr(result, collectkey, None) for result in qs]
                else:
                    qs = list(qs)
            elif params.collect == "set":
                qs = set(qs)
            elif params.collect == "dict":
                collectkey = params.collectkey
                qs = OrderedDict((getattr(obj, collectkey), obj)
                                 for obj in qs if hasattr(obj, collectkey))
            elif params.collect == "dict_sequence":
                qs = OrderedDict(qs)
        else:
            qs = MoyaQuerySet(qs, table_class, dbsession)

        self.set_context(context, params.dst, qs)


def _flatten_result(obj):
    if isinstance(obj, (ResultProxy, list, tuple)):
        return [_flatten_result(i) for i in obj]
    if isinstance(obj, RowProxy):
        return OrderedDict((k, v) for k, v in obj.items())
    return obj


@implements_bool
class MoyaResultFetcher(object):
    __moya_exposed_attributes__ = ['one', 'all', 'scalar']

    def __init__(self, results):
        self._results = results

    def __moyarepr__(self, context):
        return "<fetcher>"

    def __getitem__(self, k):
        if isinstance(k, text_type):
            if k == 'one':
                return self.one
            elif k == 'all':
                return self.all
            elif k == 'scalar':
                return self.scalar
            else:
                return KeyError(k)
        elif isinstance(k, number_types):
            i = int(k)
            if i <= 0:
                raise KeyError(k)
            try:
                return _flatten_result(self._results.fetchmany(i))
            except:
                return []
        raise KeyError(i)

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return 3

    def __bool__(self):
        return True

    def keys(self):
        return ['one', 'all', 'scalar']

    def values(self):
        return [self.one, self.all, self.scalar]

    def items(self):
        return zip(self.keys(), self.values())

    @property
    def one(self):
        try:
            return _flatten_result(self._results.fetchone())
        except:
            return None

    @property
    def all(self):
        try:
            return _flatten_result(self._results.fetchall())
        except:
            return []

    @property
    def scalar(self):
        try:
            return self._results.scalar()
        except:
            return None


@implements_bool
class MoyaResultProxy(interface.AttributeExposer):
    """A proxy to SQL Alchemy's ResultProxy"""

    __moya_exposed_attributes__ = ['rowcount',
                                   'rowkeys',
                                   'fetch']

    def __init__(self, results, sql):
        self._results = results
        self.sql = sql.strip()
        self.fetch = MoyaResultFetcher(results)

    def __bool__(self):
        return bool(self.rowcount)

    def __moyarepr__(self, context):
        return "<results {}>".format(context.to_expr(self.sql))

    def __iter__(self):
        return iter(_flatten_result(r) for r in self._results.fetchall())

    @property
    def rowcount(self):
        return self._results.rowcount

    @property
    def rowkeys(self):
        return self._results.keys()


class SQL(DBDataSetter):
    """
    This tag executes raw SQL and returns a [i]results[/i] object.

    Results objects have the properties [c]rowcount[/c] (number of rows matched), [c]rowkeys[/c] (list of field names), and [c]fetch[/c] (an interface to retrieve results).

    You can retrieve all rows with [c]results.fetch.all[/c], or a single row at a time with [c]results.fetch.one[/c]. You can get a batch of a rows by using an integer index. For example, [c]results.fetch.10[/c] retrieves the next 10 rows.

    If your query returns a scalar value, you can retrieve it with [c]results.fetch.scalar[/c].

    """

    class Help:
        synopsis = "execute raw sql"
        example = """
        <db:sql dst="results" let:username="'John'">
            select * from auth_user where auth_user.username=:username;
        </db:sql>
        <echo obj="results.fetch.one"/>

        """

    db = Attribute("Database", default="_default")
    bind = Attribute("Parameters to bind to SQL", type="expression", default=None)

    @wrap_db_errors
    def get_value(self, context):
        params = self.get_parameters(context)
        sql_text = self.text
        sql = text(sql_text)
        sql_params = self.bind(context) or {}
        if not isinstance(sql_params, dict):
            self.throw('bad-value.wrong-type', "bind must be a dict or dict-like object")
        sql_params.update(self.get_let_map(context))
        dbsession = self.get_session(context, params.db)
        result = dbsession.execute(sql, sql_params)
        result = MoyaResultProxy(result, sql_text)
        return result


class Update(DBDataSetter):
    """
    Update a query set with database expressions. Not to be confused with [tag]{}update[/tag] in the default namespace.

    """

    class Help:
        synopsis = """update fields in a query"""
        example = """
        <db:query model="#Vote" filter="#Vote.topic=='moya'" dst="votes"/>
        <db:update src="votes" let:topic="#Vote.score + 1" />
        """

    src = Attribute("Queryset", required=True, type="expression", metavar="QUERYSET")
    db = Attribute("Database", default="_default")
    synchronize = Attribute("Synchronize session strategy", choices=['none', 'fetch', 'evaulate'], default="fetch")

    def logic(self, context):
        params = self.get_parameters(context)
        dbsession = self.get_session(context, params.db)
        qs = self._qs(context, dbsession, params.src)
        let = self.get_let_map_eval(context, lambda l: DBExpression(l).eval(self.archive, context))
        sync = params.synchronize
        if sync == 'none':
            sync = None
        with dbsession.manage(self):
            qs.update(let, synchronize_session=sync)


class Commit(DBContextElement):
    """
    Commit any pending transaction. This will [i]flush[/i] db operations to the database. If you have create new objects and you want to know their [i]primary key[/i] (id), you will need to commit them to the database.

    Note, that if this tag is called from within a [tag db]transaction[/tag] tag, nothing will be committed until the end of the [tag db]transaction[/tag].

    """

    class Help:
        synopsis = """commit the current transaction"""
        example = """
        <db:create model="model.shorturl" obj="form.data" dst="shorturl"/>
        <db:commit />
        <echo>${shorturl.id}</echo>
        """

    db = Attribute("Database", default="_default")

    @wrap_db_errors
    def logic(self, context):
        dbsession = self.get_session(context, self.db(context))
        with dbsession.manage(self):
            pass


class RollBack(DBContextElement):
    """
    This tag will rollback a transaction, and restore the database to the state where it was previously commited.

    """

    class Help:
        synopsis = """roll back the current transactions"""

    db = Attribute("Database", default="_default")

    @wrap_db_errors
    def logic(self, context):
        dbsession = self.get_session(context)
        dbsession.rollback()


class Check(DBContextElement):
    """Check connection to DB, throw db.no-connection if connection failed. This tag is used by Moya Debug, it is unlikely to be generally useful."""

    class Help:
        synopsis = """check connection to the database"""

    db = Attribute("Database", default="_default")

    def logic(self, context):
        dbsession = self.get_session(context, self.db(context))
        try:
            dbsession.connection()
        except Exception as e:
            self.throw("db.no-connection", text_type(e))


class Atomic(DBContextElement):
    """
    Makes the enclosed block [i]atomic[/i].

    An atomic block works much like [tag db]transaction[/tag], but uses the databases SAVEPOINT feature to better handle nested atomic blocks.

    """

    class Help:
        synopsis = """mark a block as being atomic"""
        example = """
        <!--- taken from Moya Social Links -->
        <db:atomic>
            <db:get model="#Link" let:id="link" dst="link" />
            <db:get model="#Vote" let:link="link" dst="vote" />
            <db:create if="not vote"
                model="#Vote" let:link="link" let:user=".user" let:score="score" dst="vote" />
            <let link.score="link.score - vote.score" vote.score="score" />
            <let link.score="link.score + vote.score" />
        </db:atomic>

        """

    db = Attribute("Database", default="_default")

    @wrap_db_errors
    def logic(self, context):
        dbsession = self.get_session(context, self.db(context))

        if dbsession.engine.driver == 'pysqlite':
            log.warning('sqlite driver does not support <atomic>')
            try:
                yield DeferNodeContents(self)
            except Exception as e:
                log.warning('exception in <atomic> block ()'.format(e))
                raise
        else:
            session = dbsession.session
            session.begin_nested()
            try:
                yield DeferNodeContents(self)
            except Exception as e:
                session.rollback()
                raise
            else:
                session.commit()


class Transaction(DBContextElement):
    """
    Executes the enclosed block in a single transaction.

    If the block executes successfully, the changes will be committed. If an exception is thrown, the changes will be rolled back.

    Note that databases related exceptions in the enclosed black won't be thrown until the end of the transaction.

    In the case of nested transactions (a transaction inside a transactions), only the outer-most transaction will actually commit the changes. For more granular control over transactions, the [tag db]atomic[/tag] tag is preferred.

2260
    """

    class Help:
        synopsis = "commit changes to the database"

    db = Attribute("Database", default="_default")

    @wrap_db_errors
    def logic(self, context):
        dbsession = self.get_session(context, self.db(context))
        with dbsession.manage(self):
            yield DeferNodeContents(self)


class UniqueTogether(DBContextElement):
    xmlns = namespaces.db

    class Help:
        synopsis = """require combinations of fields to be unique"""

    fields = Attribute("Fields", type="commalist", required=False, default=None)

    def document_finalize(self, context):
        fields = self.fields(context)
        if fields is None:
            fields = []
            for child in self.children():
                if isinstance(child, (FieldElement, _ForeignKey)):
                    fields.append(child.dbname)

        fields = list(set(fields))

        model = self.get_ancestor((self.xmlns, "model"))
        model.add_constraint(UniqueConstraint(*fields))
