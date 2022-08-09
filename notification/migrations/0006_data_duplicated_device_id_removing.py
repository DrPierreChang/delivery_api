# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


def remove_duplicates_in_devices(apps, schema_editor):
    for model in [apps.get_model("notification", "GCMDevice"), apps.get_model("notification", "APNSDevice")]:
        device_ids = set(model.objects.values_list('device_id'))
        for device_id in device_ids:
            devices = model.objects.filter(device_id=device_id[0])
            last_device = devices.last()
            if last_device:
                devices = devices.exclude(id=last_device.id)
            devices.delete()


def remove_duplicates_in_devices_pass(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0005_auto_20150105_0850'),
    ]

    operations = [
        migrations.RunPython(remove_duplicates_in_devices, remove_duplicates_in_devices_pass),
    ]
