# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-02-18 14:10
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0013_auto_20160218_1048'),
    ]

    operations = [
        migrations.AlterField(
            model_name='member',
            name='role',
            field=models.PositiveIntegerField(choices=[(16, 'Admin'), (8, 'Manager'), (1, 'Driver'), (0, 'OUT_OF_ROLE')], default=0),
        ),
    ]