# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-02-18 10:48
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0012_member_last_ping'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='invite',
            name='position',
        ),
        migrations.AddField(
            model_name='member',
            name='role',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='invite',
            name='position',
            field=models.PositiveIntegerField(choices=[(16, 'Admin'), (8, 'Manager'), (1, 'Driver'), (0, 'OUT_OF_ROLE')], default=1),
        ),
    ]
