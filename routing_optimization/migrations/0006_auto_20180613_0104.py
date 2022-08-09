# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-06-05 11:39
from __future__ import unicode_literals

import django.contrib.postgres.fields
from django.db import migrations, models


def fill_days_field(apps, schema):
    RouteOptimization = apps.get_model('routing_optimization', 'routeoptimization')
    for ro in RouteOptimization.objects.all():
        ro.days = [ro.day]
        ro.save(update_fields=['days'])


def fill_day_field_back(apps, schema):
    RouteOptimization = apps.get_model('routing_optimization', 'routeoptimization')
    for ro in RouteOptimization.objects.all():
        ro.day = ro.days[0]
        ro.save(update_fields=['day'])


class Migration(migrations.Migration):

    dependencies = [
        ('routing_optimization', '0005_auto_20180502_1819'),
    ]

    operations = [
        migrations.AddField(
            model_name='routeoptimization',
            name='is_individual',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='routeoptimization',
            name='days',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.DateField(), default=list, size=None),
        ),
        migrations.RunPython(fill_days_field, fill_day_field_back),
    ]