# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2018-02-08 08:00
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0018_auto_20180202_0004'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='dispatch_time',
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='message',
            name='is_sent',
            field=models.BooleanField(default=False),
        ),
    ]
