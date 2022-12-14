# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-07-13 10:09
from __future__ import unicode_literals

import calendar
import datetime

import pytz
from django.db import migrations

import radaro_utils


def convert_to_datetime(apps, schema_migration):
    DriverLocation = apps.get_model('driver', 'DriverLocation')
    for loc in DriverLocation.objects.all():
        loc.temp_timestamp = pytz.utc.localize(datetime.datetime.utcfromtimestamp(loc.timestamp)) \
            if loc.timestamp else loc.created_at
        loc.save()


def convert_to_timestamp(apps, schema_migration):
    DriverLocation = apps.get_model('driver', 'DriverLocation')
    for loc in DriverLocation.objects.all():
        ms = loc.temp_timestamp.microsecond / 1000000
        loc.timestamp = calendar.timegm(loc.temp_timestamp.utctimetuple()) + ms
        loc.save()


class Migration(migrations.Migration):

    dependencies = [
        ('driver', '0010_driverlocation_offline'),
    ]

    operations = [
        migrations.AddField(
            model_name='driverlocation',
            name='temp_timestamp',
            field=radaro_utils.fields.CustomDateTimeField(auto_now_add=True),
        ),
        migrations.RunPython(convert_to_datetime, convert_to_timestamp),
    ]
