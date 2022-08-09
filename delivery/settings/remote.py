from __future__ import absolute_import

import logging
import warnings

from delivery.settings.base import *

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger, LoggingIntegration

from delivery.settings import env_vars

from .saml import build_saml_config

# todo: remove
DEV = False
ENV = 'PROD'

DEBUG = False

USE_HTTPS = env_vars.USE_HTTPS

NEW_RELIC_ENV = env_vars.NEW_RELIC_ENV

# Enable/disable run newrelic python agent with django application.
NEWRELIC_DJANGO_ACTIVE = env_vars.NEWRELIC_DJANGO_ACTIVE

# todo: check if this really need to be in settings
# Enable/disable to run newrelic agent with celery worker daemons.
# Run `update_celery_config` fabric task to apply changes!
NEWRELIC_CELERY_ACTIVE = env_vars.NEWRELIC_CELERY_ACTIVE

# If you're going to disable availability test task, make sure you disable availability monitor test
# in synthetics tab of new relic account.
NEWRELIC_AVAILABILITY_TEST_ACTIVE = env_vars.NEWRELIC_AVAILABILITY_TEST_ACTIVE


ADMINS = (
    ('Gleb Pitsevich', 'gleb@razortheory.com'),
    ('Stanislau Kavaliou', 'stas.k@razortheory.com'),
    ('Roman Karpovich', 'roman@razortheory.com'),
    ('Valeria Shvadronova', 'valeria.sh@razortheory.com'),
)

MANAGERS = ADMINS

CURRENT_HOST = env_vars.CURRENT_HOST # todo: check code usages and replace with base_url
BASE_URL = "http{}://{}".format('s' if env_vars.USE_HTTPS else '', env_vars.CURRENT_HOST)

DATABASES['default']['HOST'] = env_vars.DB_HOST
DATABASES['default']['USER'] = env_vars.DB_USER
DATABASES['default']['PASSWORD'] = env_vars.DB_PASSWORD
if hasattr(env_vars, 'DB_NAME'):
    DATABASES['default']['NAME'] = env_vars.DB_NAME

if hasattr(env_vars, 'READ_DB_HOST'):
    DATABASES['readonly'] = copy(DATABASES['default'])
    DATABASES['readonly']['HOST'] = env_vars.READ_DB_HOST

    DATABASE_ROUTERS = ['base.utils.db_routers.SeparateReadOnlyDatabaseRouter']


# Is used in links to track order. Be careful: you may need account.radaro... which is Cloudfront
FRONTEND_URL = env_vars.FRONTEND_URL
CUSTOMER_FRONTEND_URL = env_vars.CUSTOMER_FRONTEND_URL

# We safely allow all hosts, because we don't know which host will perform health check.
# Nginx will block unneeded hosts.
ALLOWED_HOSTS = ['*']

if getattr(env_vars, 'AWS_ACCESS_KEY_ID', None):
    # S3 stuff
    STORAGE_TYPE = 's3'
    AWS_DEFAULT_ACL = 'public-read'
    AWS_QUERYSTRING_AUTH = False
    AWS_PRELOAD_METADATA = True
    AWS_S3_SECURE_URLS = True
    AWS_ACCESS_KEY_ID = env_vars.AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY = env_vars.AWS_SECRET_ACCESS_KEY
    AWS_STORAGE_BUCKET_NAME = env_vars.AWS_STORAGE_BUCKET_NAME
    AWS_S3_HOST = 's3.{0}.amazonaws.com'.format(env_vars.AWS_S3_REGION)
    # if version explicitly set, use it. some regions don't support v2 signature at all, only v4
    if env_vars.AWS_S3_SIGNATURE_VERSION:
        AWS_S3_SIGNATURE_VERSION = env_vars.AWS_S3_SIGNATURE_VERSION

    DEFAULT_FILE_STORAGE = 'delivery.settings.s3utils.MediaRootS3BotoStorage'
    STATICFILES_STORAGE = 'delivery.settings.s3utils.StaticRootS3BotoStorage'
elif getattr(env_vars, 'AZURE_ACCOUNT_NAME', None):
    # Azure storage
    STORAGE_TYPE = 'azure'
    AZURE_ACCOUNT_NAME = env_vars.AZURE_ACCOUNT_NAME
    AZURE_ACCOUNT_KEY = env_vars.AZURE_ACCOUNT_KEY
    AZURE_CONTAINER = env_vars.AZURE_CONTAINER
    AZURE_SSL = True

    DEFAULT_FILE_STORAGE = 'delivery.settings.azure_storage.MediaRootAzureStorage'
    STATICFILES_STORAGE = 'delivery.settings.azure_storage.StaticRootAzureStorage'
else:
    raise NotImplementedError('Unable to configure storage. Provide either s3 or azure config variables in env_vars')

# Are used in storage
MEDIA_FOLDER = env_vars.MEDIA_FOLDER
MEDIA_URL = '/{}/'.format(MEDIA_FOLDER)
STATIC_FOLDER = env_vars.STATIC_FOLDER
STATIC_URL = '/{}/'.format(STATIC_FOLDER)

# Cache settings

CACHES['default']['LOCATION'] = env_vars.REDIS_URL
CACHES['optimisation']['LOCATION'] = env_vars.REDIS_URL_ROUTE_OPTIMISATION


# Compressor & Cloudfront settings

USE_COMPRESSOR = env_vars.USE_COMPRESSOR
USE_CLOUDFRONT = env_vars.USE_CLOUDFRONT

if USE_CLOUDFRONT or USE_COMPRESSOR:
    AWS_HEADERS = {'Cache-Control': str('public, max-age=604800')}
    AZURE_CACHE_CONTROL = 'public, max-age=604800'

if USE_COMPRESSOR:
    ########## COMPRESSION CONFIGURATION
    INSTALLED_APPS += ('compressor',)
    STATICFILES_FINDERS += ('compressor.finders.CompressorFinder',)

    # See: http://django_compressor.readthedocs.org/en/latest/settings/#django.conf.settings.COMPRESS_ENABLED
    COMPRESS_ENABLED = True

    # See: http://django-compressor.readthedocs.org/en/latest/settings/#django.conf.settings.COMPRESS_CSS_HASHING_METHOD
    COMPRESS_CSS_HASHING_METHOD = 'content'

    COMPRESS_CSS_FILTERS = (
        'delivery.settings.abs_compress.CustomCssAbsoluteFilter',
        'compressor.filters.cssmin.CSSMinFilter'
    )

    COMPRESS_OFFLINE = True
    COMPRESS_OUTPUT_DIR = "cache"
    COMPRESS_CACHE_BACKEND = "locmem"
    COMPRESS_STORAGE = STATICFILES_STORAGE
    ########## END COMPRESSION CONFIGURATION

DEFAULT_FROM_EMAIL = SERVER_EMAIL = env_vars.EMAIL_PREFIX + ' <%s>' % env_vars.SERVER_EMAIL
EMAIL_PREFIX = env_vars.EMAIL_PREFIX
SERVER_EMAIL_FROM = env_vars.SERVER_EMAIL

# Email settings (Mandrill)
EMAIL_BACKEND = 'anymail.backends.sendgrid.EmailBackend'
ANYMAIL_SENDGRID_API_KEY = env_vars.ANYMAIL_SENDGRID_API_KEY

REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = ('rest_framework.renderers.JSONRenderer', )

# Google analytics settings
GA_ENABLED = env_vars.GA_ENABLED
GOOGLE_ANALYTICS_PROPERTY_ID = env_vars.GOOGLE_ANALYTICS_PROPERTY_ID


SMS_BACKEND = 'radaro_utils.radaro_notifications.sms.backends.rawmobility.SMSBackend'
SMS_SENDING_PARAMETERS = {
    'USER_NAME': env_vars.SMS_USER_NAME,
    'PASSWORD': env_vars.SMS_PASSWORD,
    'ORIGINATOR': env_vars.SMS_ORIGINATOR,
    'ROUTE': env_vars.SMS_ROUTE,
}

ANDROID_SMS_VERIFICATION = env_vars.ANDROID_SMS_VERIFICATION

RAWMOBILITY_API_URL = 'http://apps.rawmobility.com/gateway/api/simple/MT'

PINAX_STRIPE_PUBLIC_KEY = env_vars.PINAX_STRIPE_PUBLIC_KEY
PINAX_STRIPE_SECRET_KEY = env_vars.PINAX_STRIPE_SECRET_KEY

if env_vars.PUSH_NOTIFICATIONS_SANDBOX:
    PUSH_NOTIFICATIONS_SETTINGS.update({
        "APNS_USE_SANDBOX": True,
    })
else:
    PUSH_NOTIFICATIONS_SETTINGS.update({
        "GCM_API_KEY": env_vars.PUSH_NOTIFICATIONS_GCM_API_KEY,
        "APNS_CERTIFICATE": os.path.join(BASE_DIR, env_vars.PUSH_NOTIFICATIONS_APNS_CERTIFICATE),
    })

CORS_ORIGIN_ALLOW_ALL = False
CORS_ORIGIN_WHITELIST = env_vars.CORS_WHITELIST

# To use API
GOOGLE_API_KEY = env_vars.GOOGLE_API_KEY
GOOGLE_API_PROXY = env_vars.GOOGLE_API_PROXY if env_vars.GOOGLE_API_PROXY else None
GOOGLE_MAPS_V3_APIKEY = env_vars.GOOGLE_MAPS_V3_APIKEY
LOCATION_FIELD['provider.google.api_key'] = GOOGLE_MAPS_V3_APIKEY

RADARO_SHORTENER_TOKEN = env_vars.RADARO_SHORTENER_TOKEN

RADARO_ROUTER_URL = env_vars.RADARO_ROUTER_URL
RADARO_ROUTER_TOKEN = env_vars.RADARO_ROUTER_TOKEN

UPTIME_BOT_ACTIVE = env_vars.UPTIME_BOT_ACTIVE
UPTIME_BOT_VERIFICATION_TOKEN = env_vars.UPTIME_BOT_VERIFICATION_TOKEN

if STORAGE_TYPE == 's3':
    STATIC_URL = 'https://{}.s3.amazonaws.com/{}/'.format(AWS_STORAGE_BUCKET_NAME, STATIC_FOLDER)
elif STORAGE_TYPE == 'azure':
    STATIC_URL = 'https://{}.blob.core.windows.net/{}/{}/'.format(AZURE_ACCOUNT_NAME, AZURE_CONTAINER, STATIC_FOLDER)
else:
    raise NotImplementedError

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

ADMIN_SITE_SUPERADMINS = env_vars.ADMIN_SITE_SUPERADMINS

# Distance unit, used as default for merchants
DEFAULT_DISTANCE_SHOW_IN = env_vars.DEFAULT_DISTANCE_SHOW_IN

# Date format, used as default for merchants
DEFAULT_DATE_FORMAT = env_vars.DEFAULT_DATE_FORMAT

# Language dialect, used as default for errors/messages/CMS
LANGUAGE_CODE = env_vars.LANGUAGE_CODE

TIME_ZONE = env_vars.TIME_ZONE

CLUSTER_NAME = env_vars.CLUSTER_NAME
CLUSTER_NUMBER = env_vars.CLUSTER_NUMBER

DELIVER_ADDRESS_2_ENABLED = env_vars.DELIVER_ADDRESS_2_ENABLED

# Sentry
SENTRY_ENABLED = env_vars.SENTRY_ENABLED
if SENTRY_ENABLED:
    SENTRY_DSN = env_vars.SENTRY_DSN
    traces_sample_rate = getattr(env_vars, 'SENTRY_TRACES_SAMPLE_RATE', None)
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(middleware_spans=False),
            CeleryIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.WARNING),
        ],
        traces_sample_rate=traces_sample_rate,
        server_name=CLUSTER_NAME.replace(' ', '-').lower(),
        attach_stacktrace=True,
    )
    ignore_logger('saml2.sigver')

    def custom_formatwarning(message, category, filename, lineno, line=None):
        return f'{category.__name__}: {message}\n{filename}:{lineno}:'
    warnings.formatwarning = custom_formatwarning

    logging.captureWarnings(True)
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'verbose': {
                'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
            },
            'simple': {
                'format': '%(levelname)s %(message)s'
            },
        },
        'filters': {
            'is_dummy_optimisation': {
                '()': 'route_optimisation.logging.DummyOptimisationFilter',
            },
            'is_route_optimisation': {
                '()': 'route_optimisation.logging.OptimisationFilter',
            },
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'verbose',
            },
            'file': {
                'class': 'logging.handlers.WatchedFileHandler',
                'filename': 'logs/{}-{}.log'.format(PROJECT_NAME, DJANGO_LOG_NAME),
                'formatter': 'verbose'
            },
            'file_route_optimization': {
                'class': 'logging.FileHandler',
                'filename': 'logs/route_optimization.log',
                'formatter': 'verbose'
            },
            'optimisation': {
                'level': 'DEBUG',
                'class': 'route_optimisation.logging.OptimisationLogHandler',
                'filters': ['is_route_optimisation'],
            },
            'dummy_optimisation': {
                'level': 'DEBUG',
                'class': 'route_optimisation.logging.DummyOptimisationLogHandler',
                'filters': ['is_dummy_optimisation'],
            },
        },
        'loggers': {
            'py.warnings': {
                'level': 'WARNING',
                'handlers': ['console'],
                'propagate': True,
            },
            'django': {
                'level': 'ERROR',
                'handlers': ['console'],
                'propagate': False,
            },
            'route_optimization_logs': {
                'level': 'DEBUG',
                'handlers': ['file_route_optimization'],
                'propagate': True,
            },
            'optimisation': {
                'level': 'DEBUG',
                'handlers': ['optimisation', 'dummy_optimisation'],
                'propagate': False,
            },
            **{
                _module: {
                    'level': 'DEBUG',
                    'handlers': ['file'],
                    'propagate': True,
                }
                for _module in (
                    'base.utils.utils', 'integrations.utils', 'driver.utils.locations', 'tasks.views',
                    'radaro_utils.radaro_csv.meta', 'reporting.decorators', 'reporting.celery_tasks',
                    'merchant.celery_tasks', 'routing.google',
                )
            }
        },
    }

# SFTP server
SFTP_SERVER = env_vars.SFTP_SERVER
SFTP_USER = env_vars.SFTP_USER
SFTP_PASSWORD = env_vars.SFTP_PASSWORD
SFTP_PORT = env_vars.SFTP_PORT


# SAML
SAML_CONFIG = build_saml_config(BASE_DIR, BASE_URL, env_vars)
SAML_ALLOWED_HOSTS = env_vars.SAML_ALLOWED_HOSTS
SAML_SESSION_COOKIE_NAME = 'saml_session'
SAML_ATTRIBUTE_MAPPING = {'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress': ('email',)}
SAML_DJANGO_USER_MAIN_ATTRIBUTE = 'email'
SAML_CREATE_UNKNOWN_USER = False
SAML_ACS_FAILURE_RESPONSE_FUNCTION = 'custom_auth.saml2.utils.on_fail'


# Requests Monitoring
QUEUE_TIME_TRACKER_CLOUDWATCH_ACCESS_KEY = env_vars.CLOUDWATCH_QUEUE_TIME_ACCESS_KEY
QUEUE_TIME_TRACKER_CLOUDWATCH_SECRET_KEY = env_vars.CLOUDWATCH_QUEUE_TIME_SECRET_KEY
QUEUE_TIME_TRACKER_CLOUDWATCH_REGION = env_vars.CLOUDWATCH_QUEUE_TIME_REGION
QUEUE_TIME_TRACKER_HEADER = 'HTTP_X_REQUEST_TIME'
QUEUE_TIME_TRACKER_CLOUDWATCH_NAMESPACE = env_vars.CLOUDWATCH_QUEUE_TIME_NAMESPACE
QUEUE_TIME_TRACKER_CACHE_NAME = 'default'
QUEUE_TIME_TRACKER_CACHE_KEY_PREFIX = 'radaro'


# Route Optimisation
if hasattr(env_vars, 'ORTOOLS_SEARCH_TIME_LIMIT'):
    ORTOOLS_SEARCH_TIME_LIMIT = env_vars.ORTOOLS_SEARCH_TIME_LIMIT
if hasattr(env_vars, 'ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP'):
    ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP = env_vars.ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP
