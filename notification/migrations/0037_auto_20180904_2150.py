# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-09-04 11:50
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0036_merge_20180830_2200'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='smsmessage',
            name='polymorphic_ctype',
        ),
        migrations.DeleteModel(
            name='SMSMessage',
        ),
    ]
