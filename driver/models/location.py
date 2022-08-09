from django.db import models

from location_field.models.plain import PlainLocationField

from radaro_utils.fields import CustomDateTimeField
from routing.models import Location


class DriverLocationManager(models.Manager):
    def processed(self):
        return self.get_queryset().filter(improved_location__isnull=False)


class DriverLocation(Location):
    member = models.ForeignKey('base.Member', null=True, blank=True, related_name='location', on_delete=models.CASCADE)
    accuracy = models.FloatField(null=True, blank=True, default=0.0)
    speed = models.FloatField(null=True, blank=True, default=0.0)
    timestamp = CustomDateTimeField(auto_now_add=True)
    bearing = models.FloatField(default=0)
    improved_location = PlainLocationField(based_fields=['address'], zoom=7, default=None, null=True, blank=True)
    source = models.PositiveIntegerField(editable=False, null=True, blank=True)
    offline = models.BooleanField(default=False)

    google_request_cost = models.DecimalField(max_digits=7, decimal_places=5, null=True, blank=True)
    in_progress_orders = models.PositiveSmallIntegerField(default=0, null=True, blank=True)
    google_requests = models.PositiveSmallIntegerField(default=0, null=True, blank=True)

    objects = DriverLocationManager()

    class Meta:
        ordering = ('created_at', )

    @property
    def prepared_location(self):
        return self.improved_location or self.location


__all__ = ['DriverLocation', 'DriverLocationManager']
