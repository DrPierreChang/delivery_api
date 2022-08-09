# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0004_auto_20141205_0538'),
    ]

    operations = [
        migrations.AlterField(
            model_name='apnsdevice',
            name='device_id',
            field=models.CharField(help_text='UDID / UIDevice.identifierForVendor()', max_length=255, null=True, verbose_name='Device ID', blank=True),
        ),
        migrations.AlterField(
            model_name='gcmdevice',
            name='device_id',
            field=models.CharField(help_text='ANDROID_ID / TelephonyManager.getDeviceId() (always as hex)', max_length=255, null=True, verbose_name='Device ID', blank=True),
        ),
    ]
