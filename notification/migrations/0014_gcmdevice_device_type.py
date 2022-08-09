# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-05-10 12:59
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0013_auto_20170506_1954'),
    ]

    operations = [
        migrations.AddField(
            model_name='gcmdevice',
            name='device_type',
            field=models.CharField(choices=[('ios', 'IOS'), ('android', 'Android')], default='android', max_length=16),
        ),
    ]
