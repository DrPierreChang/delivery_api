import environ


env = environ.Env()
environ.Env.read_env()


CELERYD_DEFAULT_CONCURRENCY = env.int('CELERY_DEFAULT_CONCURRENCY', default=2)
CELERYD_PRIORITY_CONCURRENCY = env.int('CELERY_PRIORITY_CONCURRENCY', default=2)
CELERYD_SLOW_CONCURRENCY = env.int('CELERY_SLOW_CONCURRENCY', default=2)
