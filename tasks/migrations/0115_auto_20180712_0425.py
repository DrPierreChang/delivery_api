# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-07-11 18:25
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0114_auto_20180707_2354'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='orderprototype',
            name='used_serializer',
        ),
        migrations.AddField(
            model_name='bulkdelayedupload',
            name='unpack_serializer',
            field=models.CharField(choices=[('external', 'EXTERNAL'), ('csv', 'CSV')], default='csv', editable=False, max_length=256),
        ),
    ]
