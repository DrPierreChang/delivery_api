from __future__ import absolute_import
from delivery import settings

from . import base_env_vars as env_vars
from . import base_server_vars as server_vars

settings.env_vars = env_vars
settings.server_vars = server_vars

from .base import *
from .saml import build_saml_config

DEV = True
STAGING = False
PROD = False
ENV = 'DEV'

DEBUG = True
CURRENT_HOST = "127.0.0.1:8000"
CLUSTER_NAME = 'dev'
CLUSTER_NUMBER = 'dev'

USE_HTTPS = False

BASE_URL = "http://" + CURRENT_HOST

FRONTEND_HOST = "127.0.0.1:3000"
FRONTEND_URL = "http://" + FRONTEND_HOST

CUSTOMER_FRONTEND_HOST = FRONTEND_HOST
CUSTOMER_FRONTEND_URL = "http://" + CUSTOMER_FRONTEND_HOST

CELERY_TASK_ALWAYS_EAGER = True

DEFAULT_FROM_EMAIL = 'noreply@example.com'
EMAIL_PREFIX = 'Radaro'
SERVER_EMAIL = SERVER_EMAIL_FROM = DEFAULT_FROM_EMAIL
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
SMS_BACKEND = 'radaro_utils.radaro_notifications.sms.backends.console.SMSBackend'

ADMINS = (
    ('Dev Email', os.environ.get('DEV_ADMIN_EMAIL')),
)
MANAGERS = ADMINS

# Debug toolbar installation
INSTALLED_APPS += (
    'debug_toolbar',
)
MIDDLEWARE += [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    #'radaro_utils.middlewares.CProfileMiddleware',
]

CELERY_TASK_EAGER_PROPAGATES = True


UPDATE_TOKEN = False

USE_COMPRESSOR = False
COMPRESS_ENABLED = False

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

PINAX_STRIPE_PUBLIC_KEY = "pk_test_iamHmmAN0cbOz41M74LGiXY2"
PINAX_STRIPE_SECRET_KEY = "sk_test_klMiqE9t0Bxc1znf9JfmnonO"

NEW_RELIC_ENV = 'development'

REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] += ('custom_auth.authentication.I18NBasicAuthentication', )

DATABASES['default']['HOST'] = os.environ.get('DB_HOST', 'localhost')
DATABASES['default']['PORT'] = os.environ.get('DB_PORT', '5432')
DATABASES['default']['USER'] = os.environ.get('DB_USER', 'postgres')
DATABASES['default']['PASSWORD'] = os.environ.get('DB_PASSWORD', '1')
DATABASES['default']['NAME'] = os.environ.get('DB_NAME', 'delivery')

RADARO_ROUTER_URL = 'http://localhost:8001/api'
RADARO_ROUTER_TOKEN = '97404254-dfe2-4bf7-989f-1fc879324d49'

UPTIME_BOT_ACTIVE = False

# To use API
GOOGLE_API_KEY = 'AIzaSyADx1csQkZ8t2PAot24FYRLiS61a6pU9aI'
GOOGLE_API_PROXY = None
# To use maps
GOOGLE_MAPS_V3_APIKEY = GOOGLE_API_KEY
LOCATION_FIELD['provider.google.api_key'] = GOOGLE_MAPS_V3_APIKEY

NEWRELIC_DJANGO_ACTIVE = False
SENTRY_ENABLED = False

# 11 hash chars required by android app to read sms without special permissions
ANDROID_SMS_VERIFICATION = {
    'radaro': 'Msj+s18oF85',
    'nti': 'WjRAJs8+Umj',
}

SFTP_SERVER = 'localhost'
SFTP_USER = 'foo'
SFTP_PASSWORD = 'pass'
SFTP_PORT = 22

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
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
        'radaro-dev': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'optimisation': {
            'level': 'DEBUG',
            'handlers': ['optimisation', 'dummy_optimisation'],
            'propagate': False,
        },
    },
}

# SAML
SAML_CONFIG = build_saml_config(BASE_DIR, BASE_URL, env_vars)
SAML_ALLOWED_HOSTS = ['localhost']
SAML_SESSION_COOKIE_NAME = 'saml_session'

SAML_ATTRIBUTE_MAPPING = {'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress': ('email',)}
SAML_DJANGO_USER_MAIN_ATTRIBUTE = 'email'
SAML_CREATE_UNKNOWN_USER = False

SAML_ACS_FAILURE_RESPONSE_FUNCTION = 'custom_auth.saml2.utils.on_fail'
