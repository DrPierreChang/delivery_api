from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.generic import View

from .models import AvailabilityTest


class AvailabilityTestView(View):
    def get(self, request):
        result = 'Passed'
        if settings.NEWRELIC_AVAILABILITY_TEST_ACTIVE:
            try:
                test = AvailabilityTest.objects.get(primary_key='availability')
            except AvailabilityTest.DoesNotExist:
                return HttpResponse("Failed. AvailabilityTest object doesn't exist.")
            else:
                now = timezone.now()
                diff = now - test.last_access
                if diff > timedelta(minutes=15):
                    result = 'Failed. Time of the last write from the task: %s (%.2f minutes ago).' % (
                        test.last_access, diff.total_seconds() / 60)
        return HttpResponse(result)
