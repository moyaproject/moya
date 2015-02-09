from __future__ import unicode_literals
from __future__ import print_function

from ..elements.utils import attr_bool
from ..elements.boundelement import BoundElement
from ..timezone import Timezone
from ..compat import text_type
from ..context.expressiontime import ExpressionDateTime, ExpressionDate

from sqlalchemy import (Column,
                        Boolean,
                        ForeignKey,
                        BigInteger,
                        Integer,
                        SmallInteger,
                        String,
                        Float,
                        UnicodeText,
                        DateTime,
                        Sequence)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.mutable import Mutable

from sqlalchemy.types import TypeDecorator, TEXT, DATETIME, DATE
import json
from datetime import datetime, date


class JSONDict(dict):
    def __init__(self, data, json):
        self.update(data)
        self.json = json
        super(JSONDict, self).__init__()


class MoyaCustomDateTime(TypeDecorator):
    """Massage to Moya datetime"""
    impl = DATETIME

    def process_result_value(self, value, dialect):
        if isinstance(value, datetime):
            return ExpressionDateTime.from_datetime(value)
        return value


class MoyaCustomDate(TypeDecorator):
    """Massage to Moya date"""
    impl = DATE

    def process_result_value(self, value, dialect):
        if isinstance(value, date):
            return ExpressionDate.from_date(value)
        return value


class JSONEncodedDict(TypeDecorator):
    "Represents an immutable structure as a json-encoded string."

    impl = TEXT

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value


class StringMap(Mutable, dict):

    @classmethod
    def coerce(cls, key, value):
        "Convert plain dictionaries to MutableDict."

        if not isinstance(value, StringMap):
            if isinstance(value, dict):
                return StringMap(value)

            # this call will raise ValueError
            return Mutable.coerce(key, value)
        else:
            return value

    def __setitem__(self, key, value):
        "Detect dictionary set events and emit change events."

        dict.__setitem__(self, key, value)
        self.changed()

    def __delitem__(self, key):
        "Detect dictionary del events and emit change events."

        dict.__delitem__(self, key)
        self.changed()

    def update(self, map):
        dict.update(map)
        self.changed()


#MutableType.associate_with(PickleType)


# class MoyaPickleType(PickleType, Mutable):

#     def result_processor(self, dialect, coltype):
#         impl_processor = self.impl.result_processor(dialect, coltype)
#         loads = self.pickler.loads
#         if impl_processor:
#             def process(value):
#                 value = impl_processor(value)
#                 if value is None:
#                     return None
#                 return MutableObject(loads(value))
#         else:
#             def process(value):
#                 if value is None:
#                     return None
#                 return MutableObject(loads(value))
#         return process


class no_default(object):
    """Sentinal object to signify that no default is required for a column"""
    def __repr__(self):
        return "<no default>"


class MoyaDBColumn(object):
    """Contains information used to create an sqlalchemy column, and its associated abstraction"""
    def __init__(self,
                 type,
                 name,
                 default=no_default,
                 null=True,
                 blank=True,
                 primary=False,
                 index=False,
                 unique=False,
                 label=None,
                 help=None,
                 formfield=None,
                 markup=None):
        self.type = type
        self.name = name
        self.null = null
        self.blank = blank
        if default is not no_default:
            self.default = self.adapt(default)
        else:
            self.default = default
        self.primary = primary
        self.index = index
        self.unique = unique
        self.label = label
        self.help = help
        self.formfield = formfield
        self.markup = markup

    def __repr__(self):
        return "<column {} {}>".format(self.type, self.name)

    def get_dbname(self):
        return self.name

    @property
    def dbname(self):
        return self.get_dbname()

    def get_sa_columns(self):
        kwargs = dict(primary_key=self.primary,
                      nullable=self.null,
                      index=self.index,
                      unique=self.unique)
        if self.default is not no_default:
            kwargs["default"] = self.default
        yield Column(self.name,
                     self.get_sa_type(),
                     **kwargs)

    def get_properties(self, db, table_class):
        return []

    def get_sa_type(self):
        return self.dbtype()

    def adapt(self, value):
        return value

    def get_join(self, node):
        return getattr(node, self.name), None


class PKColumn(MoyaDBColumn):
    """Primary key column"""
    dbtype = Integer

    def adapt(self, value):
        return int(value)

    def get_sa_columns(self):
        sequence_name = "%s_id_seq" % self.name
        kwargs = dict(primary_key=self.primary,
                      nullable=self.null)
        if self.default is not no_default:
            kwargs["default"] = self.default
        yield Column(self.name,
                     self.get_sa_type(),
                     Sequence(sequence_name),
                     **kwargs)


class ForeignKeyColumn(MoyaDBColumn):

    def __init__(self,
                 type,
                 name,
                 ref_model,
                 ref_model_app,
                 label=None,
                 help=None,
                 default=no_default,
                 null=True,
                 blank=True,
                 primary=False,
                 index=False,
                 unique=False,
                 ondelete="CASCADE",
                 orderby=None,
                 options=None,
                 backref=None,
                 uselist=True,
                 picker=None
                 ):
        self.type = type
        self.label = label
        self.help = help
        self.ref_model = BoundElement(ref_model_app, ref_model)
        self.ref_table_name = ref_model.get_table_name(ref_model_app)
        self.name = name
        self.null = null
        self.blank = blank
        if default is not no_default:
            self.default = self.adapt(default)
        else:
            self.default = default
        self.primary = primary
        self.index = index
        self.unique = unique
        self.ondelete = "CASCADE"
        self.orderby = orderby
        self.options = options
        self.backref = backref
        self.uselist = uselist
        self.picker = picker

    def get_dbname(self):
        return self.name + '_id'

    def get_sa_columns(self):
        kwargs = dict(primary_key=self.primary,
                      nullable=self.null,
                      index=self.index,
                      unique=self.unique)
        if self.default is not no_default:
            kwargs["default"] = self.default
        name = "%s_id" % self.name
        yield Column(name,
                     Integer,
                     ForeignKey("%s.id" % self.ref_table_name, ondelete=self.ondelete),
                     **kwargs)

    def get_properties(self, model, table_class):
        "Address.id==Customer.billing_address_id"
        #join = "%s.id==%s.%s_id" % (self.ref_model.name, model.name, self.name)
        def get_join(ref_model_table_class):
            ref_model_table_class = ref_model_table_class()
            join = getattr(table_class, '%s_id' % self.name) == ref_model_table_class.id
            #join = table_class.id == getattr(ref_model_table_class, '%s_id' % self.ref_model.name.lower())
            return join

        def lazy_relationship(app, model):
            if self.backref:
                _backref = backref(self.backref, uselist=self.uselist)
            else:
                _backref = None
            ref_model_table_class = lambda: self.ref_model.element.get_table_class(self.ref_model.app)
            return relationship(ref_model_table_class(),
                                primaryjoin=lambda: get_join(ref_model_table_class),
                                remote_side=lambda: ref_model_table_class().id,
                                backref=_backref,
                                )

        yield self.name, lazy_relationship

    def get_join(self, node):
        ref_model_table_class = self.ref_model.element.get_table_class(self.ref_model.app)
        return ref_model_table_class, getattr(node, self.name)


class BoolColumn(MoyaDBColumn):
    dbtype = Boolean

    def adapt(self, value):
        return attr_bool(value)


class FloatColumn(MoyaDBColumn):
    dbtype = Float

    def adapt(self, value):
        return float(value)


class IntegerColumn(MoyaDBColumn):
    dbtype = Integer

    def adapt(self, value):
        return int(value)


class BigIntegerColumn(IntegerColumn):
    dbtype = BigInteger


class SmallIntegerColumn(IntegerColumn):
    dbtype = SmallInteger


class StringColumn(MoyaDBColumn):
    def __init__(self, type, name, length=None, choices=None, *args, **kwargs):
        self.length = length
        if choices is None:
            self.choices = choices
        else:
            self.choices = list(choices or [])
        super(StringColumn, self).__init__(type, name, *args, **kwargs)

    def get_sa_type(self):
        return String(length=self.length, convert_unicode=True)


class TimezoneType(TypeDecorator):
    '''Prefixes Unicode values with "PREFIX:" on the way in and
    strips it off on the way out.
    '''

    impl = String

    def process_bind_param(self, value, dialect):
        return text_type(value) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        try:
            return Timezone(value)
        except:
            return None

    def copy(self):
        return TimezoneType(self.impl.length)


class TimezoneColumn(StringColumn):

    def get_sa_type(self):
        return TimezoneType(length=self.length, convert_unicode=True)


class TextColumn(MoyaDBColumn):
    # def __init__(self, tag_name, name, *args, **kwargs):
    #     super(TextColumn, self).__init__(tag_name, name, *args, **kwargs)

    def get_sa_type(self):
        return UnicodeText()


class DatetimeColumn(MoyaDBColumn):
    dbtype = MoyaCustomDateTime

    def __init__(self, type, name, timezone=False, auto=False, *args, **kwargs):
        self.timezone = timezone
        self.auto = auto
        super(DatetimeColumn, self).__init__(type, name, *args, **kwargs)

    def get_sa_type(self):
        return MoyaCustomDateTime(timezone=self.timezone)


class DateColumn(MoyaDBColumn):
    dbtype = MoyaCustomDate

    def __init__(self, type, name, auto=False, *args, **kwargs):
        self.auto = auto
        super(DateColumn, self).__init__(type, name, *args, **kwargs)

    def get_sa_type(self):
        return MoyaCustomDate()


class StringMapColumn(MoyaDBColumn):
    #dbtype = PickleType

    def get_sa_type(self):
        return StringMap.as_mutable(JSONEncodedDict)
