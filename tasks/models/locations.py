from django.db import models

from routing.models.locations import Location


class OrderLocation(Location):
    raw_address = models.CharField(max_length=255, blank=True)
    secondary_address = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ('created_at',)
        unique_together = ('location', 'address', 'secondary_address', 'raw_address')

    @staticmethod
    def autocomplete_search_fields():
        return "address__icontains", "location__icontains", "description__icontains", "raw_address__icontains"

    @classmethod
    def from_location_object(cls, loc):
        location = cls.objects.filter(location=loc.location, address=loc.address, raw_address='').last()
        if location is None:
            location = cls.objects.create(location=loc.location, address=loc.address, raw_address='')
        return location
