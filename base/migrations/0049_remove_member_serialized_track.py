# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-07-07 14:59
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0048_member_serialized_track'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='member',
            name='serialized_track',
        ),
    ]
