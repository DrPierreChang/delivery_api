# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-07-10 14:32
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('driver', '0009_driverlocation_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='driverlocation',
            name='offline',
            field=models.BooleanField(default=False),
        ),
    ]