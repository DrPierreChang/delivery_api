# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2018-02-08 11:12
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0064_message'),
    ]

    operations = [
        migrations.AlterField(
            model_name='message',
            name='dispatch_time',
            field=models.DateTimeField(null=True),
        ),
    ]
