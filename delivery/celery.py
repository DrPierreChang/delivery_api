from __future__ import absolute_import

import os

import celery

# set the default Django settings module for the 'celery' program.

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'delivery.settings.dev')

from django.conf import settings

app = celery.Celery('delivery')

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

if 'redis' in settings.CELERY_BROKER_URL:
    app.conf.broker_transport_options = {'visibility_timeout': 3600 * 24 * 7}  # one week
