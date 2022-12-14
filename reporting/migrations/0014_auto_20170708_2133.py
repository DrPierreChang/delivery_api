# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-07-08 11:33
from __future__ import unicode_literals

from django.db import migrations, models

import radaro_utils.fields


def fill_created_at(apps, schema_migration):
    Event = apps.get_model('reporting', 'event')
    Event.objects.all().update(created_at=models.F('happened_at'))


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0013_exportreportinstance_created_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='created_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='happened_at',
            field=radaro_utils.fields.CustomDateTimeField(auto_now_add=True),
        ),
        migrations.RunPython(fill_created_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='event',
            name='created_at',
            field=radaro_utils.fields.CustomDateTimeField(auto_now_add=True),
        ),
        migrations.AlterModelOptions(
            name='event',
            options={'ordering': ('-happened_at',)},
        ),
    ]
