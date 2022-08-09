from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from base.fields import OneTimeValuesField


class Car(models.Model):
    SCOOTER = 0
    CAR = 1
    UTE = 2
    VAN = 3
    TRUCK = 4

    vehicle_types = (
        (SCOOTER, _('Scooter')),
        (CAR, _('Car')),
        (UTE, _('Pickup / Ute')),
        (VAN, _('Van')),
        (TRUCK, _('Truck'))
    )

    car_type = models.IntegerField(choices=vehicle_types, default=CAR)
    capacity = models.FloatField(null=True, blank=True, validators=[MinValueValidator(limit_value=0)])
    one_time_capacities = OneTimeValuesField(blank=True)

    def __str__(self):
        type_ = str(self.get_car_type_display())
        return '{0} with id: {1}'.format(type_, str(self.id))

    @classmethod
    def vehicle_types_for_version(cls, version):
        vehicles = dict(cls.vehicle_types)
        if version == 1:
            vehicles[cls.UTE] = 'Ute'
        return vehicles

    def get_capacity(self, day):
        return self.one_time_capacities.get(day, self.capacity)

    @property
    def car_type_name(self):
        return self.vehicle_types_for_version(version=2).get(self.car_type)
