# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2019-10-31 11:13
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0115_merge_20191001_2056'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='merchant',
            name='driver_jobs_ordering',
        ),
    ]
