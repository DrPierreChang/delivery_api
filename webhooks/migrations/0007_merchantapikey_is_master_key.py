# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-08-16 09:55
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webhooks', '0006_auto_20170414_1703'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchantapikey',
            name='is_master_key',
            field=models.BooleanField(default=False),
        ),
    ]
