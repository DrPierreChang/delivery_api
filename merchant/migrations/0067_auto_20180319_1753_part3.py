# -*- coding: utf-8 -*-
# Generated by Django 1.11.10 on 2018-03-19 06:53
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0067_auto_20180319_1753_part2'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='merchant',
            name='country',
        ),
    ]
