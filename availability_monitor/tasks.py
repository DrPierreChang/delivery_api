from __future__ import absolute_import

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from celery.task import periodic_task

from .models import AvailabilityTest


@periodic_task(run_every=timedelta(minutes=10))
def celery_database_access_test():
    if settings.NEWRELIC_AVAILABILITY_TEST_ACTIVE:
        now = timezone.now()
        test, _ = AvailabilityTest.objects.update_or_create(primary_key='availability', defaults={'last_access': now})
