from django.db import models

from location_field.models.plain import PlainLocationField

from routing.utils import distance_between, latlng_dict


class Location(models.Model):
    address = models.CharField(max_length=255, blank=True)
    location = PlainLocationField(based_fields=['address'], zoom=7, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=150, blank=True)

    class Meta:
        abstract = True
        ordering = ('created_at',)

    def __str__(self):
        choose_repr = self.description or self.address or str(self.location)
        return choose_repr

    @staticmethod
    def autocomplete_search_fields():
        return "address__icontains", "location__icontains", "description__icontains", "id__iexact"

    @property
    def coordinates(self):
        return tuple(map(float, self.location.split(',')))

    @property
    def dict_coordinates(self):
        return dict(zip(('lat', 'lng'), map(float, self.location.split(','))))

    def distance_to(self, location):
        from_location = latlng_dict(self.coordinates)
        to_location = latlng_dict(location.coordinates)
        return distance_between(from_location, to_location)
