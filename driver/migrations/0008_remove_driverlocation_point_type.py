# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-04-07 17:45
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('driver', '0007_driverlocation_improved_location'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='driverlocation',
            name='point_type',
        ),
    ]
