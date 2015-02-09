from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError, StatementError

from . import namespaces
from .elements.utils import attr_bool
from .compat import text_type, implements_to_string, itervalues
from . import logic

import logging
startup_log = logging.getLogger('moya.startup')
db_log = logging.getLogger('moya.db')


def dbobject(obj):
    return getattr(obj, '__moyadbobject__', lambda: obj)()


@implements_to_string
class DBEngine(object):
    def __init__(self, name, engine_name, engine, default=False):
        self.name = name
        self.engine_name = engine_name
        self.engine = engine
        self.default = default
        self.Session = sessionmaker(bind=engine)
        self.metadata = MetaData()

    def get_session(self):
        return DBSession(self.Session, self.engine)

    def __str__(self):
        return '<dbengine %s>' % self.engine_name

    def __repr__(self):
        return '<dbengine "%s">' % self.name


def _get_db_error(e):
    """Extract information from sqlalchemy error"""
    message = e.message
    info = {'sql': e.statement, 'params': e.params}
    if hasattr(e, 'orig'):
        try:
            code, message = e.orig.args
        except:
            pass
        else:
            info['code'] = code
            message = message
    return message, info


def wrap_db_errors(f):
    """Turn DB errors in to moya errors"""
    def deco(self, *args, **kwargs):
        try:
            ret = f(self, *args, **kwargs)
        except IntegrityError as e:
            message, info = _get_db_error(e)
            raise logic.MoyaException("db.integrity-error", message, info=info)
        except OperationalError as e:
            message, info = _get_db_error(e)
            raise logic.MoyaException("db.operational-error", message, info=info)
        except StatementError as e:
            message, info = _get_db_error(e)
            raise logic.MoyaException("db.statement-error", message, info=info)
        except DatabaseError as e:
            message, info = _get_db_error(e)
            raise logic.MoyaException("db.error", message, info=info)
        except Exception as e:
            raise
        else:
            return ret
    return deco


class _SessionContextManager(object):
    def __init__(self, session, element):
        self._session = session
        self._element = element

    def __enter__(self):
        self._session.enter_transaction()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._session.exit_transaction(element=self._element,
                                       exc_type=exc_type,
                                       exc_val=exc_val)


class DBSession(object):
    def __init__(self, session_factory, engine=None):
        self.session_factory = scoped_session(session_factory)
        self.engine = engine
        self._session = None
        self._transaction_level = 0

    @property
    def session(self):
        if self._session is None:
            self._session = self.session_factory()
        return self._session

    def __moyacontext__(self, context):
        return self._session

    def manage(self, element):
        self.session
        return _SessionContextManager(self, element)

    def rollback(self):
        self.session.rollback()

    def __repr__(self):
        if self.session is not None:
            return '<dbsession %s>' % self.engine
        return '<dbsession>'

    def enter_transaction(self):
        self._transaction_level += 1

    @wrap_db_errors
    def exit_transaction(self, element=None, exc_type=None, exc_val=None):
        self._transaction_level -= 1
        if exc_type is None:
            try:
                self.session.commit()
            except:
                self.session.rollback()
                raise
        else:
            self.session.rollback()

    def __getattr__(self, key):
        return getattr(self.session, key)


def add_engine(archive, name, section):
    engine_name = section['engine']
    echo = attr_bool(section.get('echo', 'n'))
    default = attr_bool(section.get('default', 'n'))

    connect_args = {}
    if engine_name.startswith('sqlite:'):
        connect_args['check_same_thread'] = False

    sqla_engine = create_engine(engine_name,
                                echo=echo,
                                pool_recycle=3600,
                                connect_args=connect_args)

    # if engine_name.startswith('sqlite:'):
    #     @event.listens_for(sqla_engine, "connect")
    #     def do_connect(dbapi_connection, connection_record):
    #         # disable pysqlite's emitting of the BEGIN statement entirely.
    #         # also stops it from emitting COMMIT before any DDL.
    #         dbapi_connection.isolation_level = None

    #     @event.listens_for(sqla_engine, "begin")
    #     def do_begin(conn):
    #         # emit our own BEGIN
    #         conn.execute("BEGIN EXCLUSIVE")

    engine = DBEngine(name, engine_name, sqla_engine, default)

    if default or not archive.database_engines:
        archive.default_db_engine = name
    archive.database_engines[name] = engine
    startup_log.debug('%r created', engine)


def get_session_map(archive):
    """Get a dictionary that maps db names on to session objects"""
    session_map = {db: engine.get_session() for db, engine in archive.database_engines.items()}
    if archive.default_db_engine is not None:
        session_map['_default'] = session_map[archive.default_db_engine]
    return session_map


def commit_sessions(context):
    count = 0
    for dbsession in context['._dbsessions'].values():
        if dbsession.session:
            try:
                dbsession.session.commit()
            except:
                db_log.exception('error committing session')
            else:
                count += 1
    return count


def rollback_sessions(context):
    count = 0
    for dbsession in context['._dbsessions'].values():
        if dbsession.session:
            try:
                dbsession.session.rollback()
            except:
                db_log.exeption('error rolling back session')
            else:
                count += 1
    return count


def sync_all(archive, console):
    if validate_all(archive, console) != 0:
        return -1
    engines = archive.database_engines
    for engine in itervalues(engines):
        if engine.default:
            default_engine = engine
            break
    else:
        default_engine = None

    apps = archive.apps.values()

    try:
        with console.progress('syncing', num_steps=len(apps), width=24) as progress:
            progress.update(None, 'building models...')
            for app in apps:
                for model in app.lib.get_elements_by_type((namespaces.db, "model")):
                    model._build_model(app)

            synced = []
            for app in apps:
                progress.update(None, 'syncing {!r}'.format(app))
                for model in app.lib.get_elements_by_type((namespaces.db, "model")):

                    engine_name = model.dbname
                    if engine_name is None:
                        engine = default_engine
                    else:
                        engine = engines[engine_name]
                    model.create_all(archive, engine, app)
                progress.step()
                synced.append(app)

            progress.update(None, 'sync complete')
    finally:
        for app in synced:
            console(text_type(app), bold=True, fg="magenta")(" synced", bold=True, fg="black").nl()

    return 0


def validate_all(archive, console=None):
    """Validates models and returns the number of fails"""

    if not archive.database_engines:
        return 0

    from .tags.db import DBModel
    fails = DBModel.validate_all(archive)

    if console is None:
        return not len(fails)

    for model, app, element, error in fails:
        if element:
            console.document_error(text_type(error),
                                   element._location,
                                   element._code,
                                   element.source_line,
                                   None)
        else:
            console.error(text_type(error))
        if hasattr(error, 'diagnosis'):
            console.table([(error.diagnosis,)])

    return len(fails)
