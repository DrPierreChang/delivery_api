# -*- coding: utf-8 -*-
# Generated by Django 1.10.3 on 2016-11-17 09:14
from __future__ import unicode_literals

from django.db import migrations

from tasks.mixins.order_status import OrderStatus


class Migration(migrations.Migration):
    def set_terminated_as_failed(apps, schema_editor):
        Order = apps.get_model('tasks', 'Order')
        Event = apps.get_model('reporting', 'Event')
        Order.objects.filter(status=OrderStatus.TERMINATED).update(status=OrderStatus.FAILED)
        Event.objects.filter(new_value=OrderStatus.TERMINATED).update(new_value=OrderStatus.FAILED)

    dependencies = [
        ('reporting', '0009_auto_20161020_2021'),
        ('tasks', '0056_order_geofence_entered'),
    ]

    operations = [
        migrations.RunPython(set_terminated_as_failed, reverse_code=migrations.RunPython.noop)
    ]
