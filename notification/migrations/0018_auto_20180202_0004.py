# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2018-02-01 13:04
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0017_auto_20180201_0122'),
    ]

    operations = [
        migrations.AlterField(
            model_name='message',
            name='sender',
            field=models.CharField(default='Radaro', max_length=40),
        ),
    ]