# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-07-05 14:24
from __future__ import unicode_literals

from django.db import migrations
import jsonfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0107_merge_20180322_1914'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='serialized_track',
            field=jsonfield.fields.JSONField(default=list),
        ),
    ]
