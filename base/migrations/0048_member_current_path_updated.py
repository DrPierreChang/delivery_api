# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-06-28 14:58
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0047_auto_20170421_1733'),
    ]

    operations = [
        migrations.AddField(
            model_name='member',
            name='current_path_updated',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
