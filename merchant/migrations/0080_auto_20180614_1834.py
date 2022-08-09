# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-06-14 08:34
from __future__ import unicode_literals

from django.db import migrations
import radaro_utils.radaro_phone.models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0079_merge_20180523_2141'),
    ]

    operations = [
        migrations.AlterField(
            model_name='merchant',
            name='phone',
            field=radaro_utils.radaro_phone.models.PhoneField(blank=True, max_length=128),
        ),
        migrations.AlterField(
            model_name='subbranding',
            name='phone',
            field=radaro_utils.radaro_phone.models.PhoneField(blank=True, max_length=128),
        ),
    ]