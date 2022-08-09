# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-06-14 08:34
from __future__ import unicode_literals

from django.db import migrations
import radaro_utils.radaro_phone.models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0057_auto_20180518_1842'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invite',
            name='phone',
            field=radaro_utils.radaro_phone.models.PhoneField(max_length=128, unique=True),
        ),
        migrations.AlterField(
            model_name='member',
            name='phone',
            field=radaro_utils.radaro_phone.models.PhoneField(max_length=128),
        ),
    ]