from functools import wraps

from django.conf import settings
from django.db.transaction import get_connection

try:
    from threading import local
except ImportError:
    from _threading_local import local


threadlocal = local()


class SeparateReadOnlyDatabaseRouter(object):
    def db_for_read(self, model, **hints):
        conn = get_connection('default')
        if conn.in_atomic_block:
            return 'default'

        db_name = get_thread_local('DB_FOR_READ_ONLY', None)
        if db_name and db_name in settings.DATABASES:
            return db_name

        return 'default'

    def db_for_write(self, model, **hints):
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return db == 'default'


class use_db_for_reads(object):
    def __init__(self, database_name):
        self.database_name = database_name

    def __enter__(self):
        setattr(threadlocal, 'DB_FOR_READ_ONLY', self.database_name)

    def __exit__(self, exc_type, exc_value, traceback):
        setattr(threadlocal, 'DB_FOR_READ_ONLY', None)

    def __call__(self, func):
        @wraps(func)
        def inner(*args, **kwargs):
            return func(*args, **kwargs)
        return inner


def get_thread_local(attr, default=None):
    return getattr(threadlocal, attr, default)


def use_readonly_db(func):
    def wrapper(*args, **kwargs):
        with use_db_for_reads('readonly'):
            return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper
