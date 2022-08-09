import os

# keys, credentials, third party service urls, etc.

CURRENT_HOST = ''
USE_HTTPS = False

NEW_RELIC_ENV = ''
NEW_RELIC_LICENSE_KEY = ''

# Enable/disable run newrelic python agent with django application.
NEWRELIC_DJANGO_ACTIVE = False

# Enable/disable to run newrelic agent with celery worker daemons.
# Run `update_celery_config` fabric task to apply changes!
NEWRELIC_CELERY_ACTIVE = False

# If you're going to disable availability test task, make sure you disable availability monitor test
# in synthetics tab of new relic account.
NEWRELIC_AVAILABILITY_TEST_ACTIVE = False


DB_HOST = ''
DB_USER = ''
DB_PASSWORD = ''

USE_COMPRESSOR = False
USE_CLOUDFRONT = False

AWS_STORAGE_BUCKET_NAME = ''
AWS_ACCESS_KEY_ID = ''
AWS_SECRET_ACCESS_KEY = ''

MEDIA_FOLDER = 'media'
STATIC_FOLDER = 'static'

FRONTEND_URL = ''
CUSTOMER_FRONTEND_URL = ''

REDIS_URL = os.environ.get('REDIS_DB', 'redis://127.0.0.1:6379/1')

EMAIL_PREFIX = 'Radaro'
SERVER_EMAIL = 'noreply@example.com'

EMAIL_HOST = ''
EMAIL_PORT = 0
EMAIL_HOST_USER = ''
EMAIL_HOST_PASSWORD = ''

SMS_USER_NAME = ''
SMS_PASSWORD = ''
SMS_ORIGINATOR = ''
SMS_ROUTE = ''

PINAX_STRIPE_PUBLIC_KEY = ''
PINAX_STRIPE_SECRET_KEY = ''

PUSH_NOTIFICATIONS_SANDBOX = False
PUSH_NOTIFICATIONS_GCM_API_KEY = ''
PUSH_NOTIFICATIONS_APNS_CERTIFICATE = ''

CORS_WHITELIST = ()

GOOGLE_API_KEY = ''
GOOGLE_MAPS_V3_APIKEY = ''

RADARO_SHORTENER_TOKEN = ''

RADARO_ROUTER_URL = ''
RADARO_ROUTER_TOKEN = ''

UPTIME_BOT_ACTIVE = False
UPTIME_BOT_VERIFICATION_TOKEN = ''

GA_ENABLED = False
GOOGLE_ANALYTICS_PROPERTY_ID = ''

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'amqp://guest@localhost//')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://127.0.0.1:6379/3')
CELERYD_DEFAULT_CONCURRENCY = 1
CELERYD_SLOW_CONCURRENCY = 2
CELERYD_PRIORITY_CONCURRENCY = 3

ANYMAIL_SENDGRID_API_KEY = ''

SENTRY_ENABLED = False
SENTRY_DSN = ''

ANDROID_SMS_VERIFICATION = {}

SFTP_SERVER = ''
SFTP_USER = ''
SFTP_PASSWORD = ''
SFTP_PORT = ''

CLUSTER_NAME = 'dev'

SAML_ALLOWED_HOSTS = []
