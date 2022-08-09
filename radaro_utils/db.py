from django.db import models
from django.db.models.functions import TruncDate
from django.db.transaction import Atomic, get_connection


class LockMode:
    ACCESS_EXCLUSIVE = 'ACCESS EXCLUSIVE'
    EXCLUSIVE = 'EXCLUSIVE'


class LockedAtomicTransaction(Atomic):
    """
    Does a atomic transaction, but also locks the entire table for any transactions, for the duration of this
    transaction. Although this is the only way to avoid concurrency issues in certain situations, it should be used with
    caution, since it has impacts on performance.
    """
    def __init__(self, model, lock_mode=None, using=None, savepoint=None):
        super(LockedAtomicTransaction, self).__init__(using, savepoint)
        self.lock_model = model
        # ACCESS EXCLUSIVE is the default table lock mode in PostgreSQL
        self.lock_mode = lock_mode or LockMode.ACCESS_EXCLUSIVE

    def __enter__(self):
        super(LockedAtomicTransaction, self).__enter__()
        cursor = None
        connection = get_connection(self.using)
        if connection.settings_dict['ENGINE'] != 'django.db.backends.postgresql_psycopg2':
            raise Exception('Only django.db.backends.postgresql_psycopg2 backend is supported '
                            'by LockedAtomicTransaction')
        try:
            cursor = connection.cursor()
            cursor.execute(
                'LOCK TABLE {db_table_name} IN {lock_mode} MODE'.format(db_table_name=self.lock_model._meta.db_table,
                                                                        lock_mode=self.lock_mode)
            )
        finally:
            if cursor and not cursor.closed:
                cursor.close()


class DistanceFunc(models.Func):
    template = '''
        (SELECT round((point((string_to_array(location, ','))[2] || ',' ||
                (string_to_array(location, ','))[1]) <@> point(%(lon)s || ',' || %(lat)s))::numeric, 3)
        FROM %(from_table_name)s
        WHERE %(from_table_name)s.id = %(current_table_name)s.%(field_name)s)'''
    output_field = models.FloatField()

    def __init__(self, latitude, longitude, from_model, location_field, **extra):
        extra['lon'] = longitude
        extra['lat'] = latitude
        extra['from_table_name'] = location_field.field.related_model._meta.db_table
        extra['current_table_name'] = from_model._meta.db_table
        extra['field_name'] = location_field.field.column
        super(DistanceFunc, self).__init__(**extra)


class RoundFunc(models.Func):
    function = 'ROUND'
    arity = 2


class TruncDateFunc(TruncDate):
    """
    Truncates date value using explicitly specified ``tzinfo`` argument.
    """
    def as_sql(self, compiler, connection):
        lhs, lhs_params = compiler.compile(self.lhs)
        tzname = self.get_tzname()
        sql = connection.ops.datetime_cast_date_sql(lhs, tzname)
        return sql, lhs_params
