# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2019-01-22 12:06
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('routing_optimization', '0010_merge_20180810_1743'),
    ]

    operations = [
        migrations.AddField(
            model_name='routeoptimization',
            name='is_removed',
            field=models.BooleanField(default=False),
        ),
    ]
