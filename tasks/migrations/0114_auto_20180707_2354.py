# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-07-07 13:54
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0113_remove_bulkdelayedupload_type'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='orderprototype',
            options={'ordering': ('id',)},
        ),
    ]
