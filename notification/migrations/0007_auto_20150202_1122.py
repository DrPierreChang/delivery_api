# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0006_data_duplicated_device_id_removing'),
    ]

    operations = [
        migrations.AlterField(
            model_name='apnsdevice',
            name='device_id',
            field=models.CharField(null=True, max_length=255, blank=True, help_text='UDID / UIDevice.identifierForVendor()', unique=True, verbose_name='Device ID'),
        ),
        migrations.AlterField(
            model_name='gcmdevice',
            name='device_id',
            field=models.CharField(null=True, max_length=255, blank=True, help_text='ANDROID_ID / TelephonyManager.getDeviceId() (always as hex)', unique=True, verbose_name='Device ID'),
        ),
    ]
