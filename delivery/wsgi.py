"""
WSGI config for django_19_test project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

from request_time_tracker.django_wsgi import CloudWatchQueueTimeTracker


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_19_test.settings")

application = get_wsgi_application()
application = CloudWatchQueueTimeTracker(application)

from django.conf import settings

if settings.NEWRELIC_DJANGO_ACTIVE:
    import newrelic.agent
    newrelic.agent.initialize(settings.NEWRELIC_INI, environment=settings.NEW_RELIC_ENV)
    application = newrelic.agent.WSGIApplicationWrapper(application)

