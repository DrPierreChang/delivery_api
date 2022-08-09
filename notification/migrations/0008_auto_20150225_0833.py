# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0007_auto_20150202_1122'),
    ]

    operations = [
        migrations.AlterField(
            model_name='apnsdevice',
            name='device_id',
            field=models.CharField(help_text='UDID / UIDevice.identifierForVendor()', max_length=255, unique=True, null=True, verbose_name='Device ID'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='gcmdevice',
            name='device_id',
            field=models.CharField(help_text='ANDROID_ID / TelephonyManager.getDeviceId() (always as hex)', max_length=255, unique=True, null=True, verbose_name='Device ID'),
            preserve_default=True,
        ),
    ]
