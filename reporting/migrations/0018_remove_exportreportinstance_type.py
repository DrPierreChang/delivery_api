# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-06-12 08:59
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0017_event_detailed_dump'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='exportreportinstance',
            name='type',
        ),
    ]