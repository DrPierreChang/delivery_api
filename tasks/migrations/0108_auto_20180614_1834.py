# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-06-14 08:34
from __future__ import unicode_literals

from django.db import migrations
import radaro_utils.radaro_phone.models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0107_merge_20180322_1914'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customer',
            name='phone',
            field=radaro_utils.radaro_phone.models.PhoneField(blank=True, max_length=128, null=True),
        ),
    ]
