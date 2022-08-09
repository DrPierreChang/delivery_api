from __future__ import unicode_literals

import random

from django.db import models

from radaro_utils.db import DistanceFunc
from routing.models.locations import Location

from .merchant import Merchant


class HubLocation(Location):
    class Meta:
        ordering = ('created_at', )


class HubQuerySet(models.QuerySet):
    def order_by_distance(self, latitude, longitude):
        distance_calculation = DistanceFunc(latitude, longitude, self.model, Hub.location)
        return self.annotate(distance=distance_calculation).order_by('distance')


class Hub(models.Model):
    OPEN = 'open'
    CLOSED = 'closed'

    statuses = (
        (OPEN, 'open'),
        (CLOSED, 'closed')
    )

    untracked_for_events = ()

    name = models.CharField(max_length=256, null=True, blank=True)
    phone = models.CharField(blank=True, null=True, max_length=40)
    location = models.ForeignKey(HubLocation, null=False, blank=False, on_delete=models.PROTECT)
    merchant = models.ForeignKey(Merchant, null=False, blank=False, on_delete=models.PROTECT)
    status = models.CharField(max_length=64, choices=statuses, default=OPEN)
    drivers = models.ManyToManyField('base.Member', through='DriverHub', related_name='wayback_hubs')

    objects = HubQuerySet.as_manager()

    def save(self, *args, **kwargs):
        # TODO: now phone-unique validation for hub in hub's serializer.
        # Move it to db model's validator after implementing models-validation-improvements-2 branch

        if not self.name:
            self.name = 'Hub #{}'.format(random.randint(1, 10000), )
        super(Hub, self).save(*args, **kwargs)

    def __str__(self):
        return self.name

    @staticmethod
    def autocomplete_search_fields():
        return "name__icontains", "phone__icontains", "id__iexact"


class DriverHub(models.Model):
    hub = models.ForeignKey('merchant.Hub', related_name='driverhub_hub', on_delete=models.CASCADE)
    driver = models.ForeignKey('base.Member', related_name='driverhub_driver', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('hub', 'driver')

    def __str__(self):
        return "Hub: {hub}, Driver: {driver}".format(hub=self.hub.name, driver=self.driver.full_name)


__all__ = ['Hub', 'HubLocation', 'DriverHub']
