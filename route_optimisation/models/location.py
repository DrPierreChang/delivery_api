from django.conf import settings
from django.db import transaction

from routing.google import merchant_registry
from routing.models import Location


class DriverRouteLocation(Location):
    class Meta:
        ordering = ('created_at', )

    def save(self, *args, **kwargs):
        is_created = not self.id
        super(DriverRouteLocation, self).save(*args, **kwargs)
        if is_created:
            merchant = merchant_registry.get_merchant()
            merchant_id = merchant.id if merchant else None

            from route_optimisation.celery_tasks import reverse_address_for_driver_route_location
            callback = lambda: reverse_address_for_driver_route_location.delay(self.id, merchant_id)
            callback() if settings.TESTING_MODE else transaction.on_commit(callback)
