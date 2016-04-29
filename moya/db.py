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
from .console import Cell

import weakref
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
        #self.Session = sessionmaker(bind=engine)  # expire_on_commit
        self.session_factory = sessionmaker(bind=engine)
        self.metadata = MetaData()
        self.table_names = set()

    def get_session(self):
        return DBSession(self.session_factory, self.engine)

    def __str__(self):
        return '<dbengine %s>' % self.engine_name

    def __repr__(self):
        return '<dbengine "%s">' % self.name


def _get_db_error(e):
    """Extract information from sqlalchemy error"""
    message = getattr(e, 'message', text_type(e))
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
            raise logic.MoyaException("db.statement-error", message, info=info, diagnosis="This error can occur if the models haven't been created in the database.\n\nDo you need to run **moya db sync**?")
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
        self.session_factory = session_factory
        self._engine = weakref.ref(engine) if engine is not None else None
        self._session = None
        self._transaction_level = 0

    @property
    def engine(self):
        return self._engine() if self._engine is not None else None

    @property
    def session(self):
        if self._session is None:
            self._session = self.session_factory()
        return self._session

    def close(self):
        if self._session:
            self.session.close()
            self._session = None

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
            if self._transaction_level == 0:
                try:
                    self.session.commit()
                except:
                    self.session.rollback()
                    raise
        else:
            self.session.rollback()
            self._transaction_level = 0

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


def commit_sessions(context, close=True):
    count = 0
    for dbsession in context['._dbsessions'].values():
        if dbsession.session:
            try:
                # db_log.debug('committing %s', dbsession)
                dbsession.session.commit()
            except:
                db_log.exception('error committing session')
            else:
                count += 1
            if close:
                try:
                    dbsession.close()
                except:
                    db_log.exception('error closing session')
    return count


def rollback_sessions(context, close=True):
    count = 0
    for dbsession in context['._dbsessions'].values():
        if dbsession.session:
            try:
                # db_log.debug('rolling back %s', dbsession)
                dbsession.session.rollback()
            except:
                db_log.exception('error rolling back session')
            else:
                count += 1
            if close:
                try:
                    dbsession.close()
                except:
                    db_log.exception('error closing session')
    return count


def close_sessions(context):
    """Close db sessions."""
    for dbsession in context['._dbsessions'].values():
        if dbsession.session:
            try:
                dbsession.close()
            except:
                db_log.exception('error closing session')



def sync_all(archive, console, summary=True):
    if validate_all(archive, console) != 0:
        return -1
    engines = archive.database_engines
    if not engines:
        return 0
    for engine in itervalues(engines):
        if engine.default:
            default_engine = engine
            break
    else:
        default_engine = None

    apps = archive.apps.values()

    synced = []
    try:
        with console.progress('syncing', num_steps=len(apps), width=24) as progress:
            progress.update(None, 'building models...')
            for app in apps:
                for model in app.lib.get_elements_by_type((namespaces.db, "model")):
                    model._build_model(app)

            for app in apps:
                progress.update(None, 'syncing {!r}'.format(app))
                count = 0
                for model in app.lib.get_elements_by_type((namespaces.db, "model")):

                    engine_name = model.dbname
                    if engine_name is None:
                        engine = default_engine
                    else:
                        engine = engines[engine_name]
                    model.create_all(archive, engine, app)
                    count += 1
                progress.step()
                synced.append((app, count))

            progress.update(None, 'db sync complete')
    finally:
        if summary:
            table = []
            for app, count in synced:
                table.append((Cell(text_type(app), fg="magenta", bold=True), Cell("{}".format(count) if count else "", bold=True)))
            console.table(table, header_row=["app", "synced"], dividers=True, grid=True)

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
