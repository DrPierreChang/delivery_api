from django.contrib.postgres.fields import JSONField
from django.db import models


class SKID(models.Model):
    CENTIMETERS = 'cm'
    INCHES = 'in'
    size_units = (
        (CENTIMETERS, 'Centimeters'),
        (INCHES, 'Inches'),
    )

    KILOGRAMS = 'kg'
    POUNDS = 'lb'
    weight_units = (
        (KILOGRAMS, 'Kilograms'),
        (POUNDS, 'Pounds'),
    )

    ADDED = 'added'
    EDITED = 'edited'
    DELETED = 'deleted'
    driver_change_choices = (
        (ADDED, 'Added'),
        (EDITED, 'Edited'),
        (DELETED, 'Deleted'),
    )

    order = models.ForeignKey('tasks.Order', related_name='skids', on_delete=models.CASCADE)
    name = models.CharField(max_length=256)
    width = models.FloatField()
    height = models.FloatField()
    length = models.FloatField()
    weight = models.FloatField()
    quantity = models.IntegerField(default=1)

    sizes_unit = models.CharField(choices=size_units, default=CENTIMETERS, max_length=10)
    weight_unit = models.CharField(choices=weight_units, default=KILOGRAMS, max_length=10)

    driver_changes = models.CharField(choices=driver_change_choices, max_length=20, null=True, blank=True, default=None)
    original_skid = JSONField(null=True, blank=True, default=None)

    class Meta:
        ordering = ['id']
