# -*- coding: utf-8 -*-
# Generated by Django 1.10.3 on 2016-11-24 15:25
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0035_auto_20160907_1710'),
    ]

    operations = [
        migrations.AddField(
            model_name='member',
            name='member_id',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True),
        ),
    ]
