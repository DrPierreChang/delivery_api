# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-03-01 08:51
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0015_auto_20160229_1036'),
    ]

    operations = [
        migrations.AddField(
            model_name='invite',
            name='token',
            field=models.CharField(blank=True, db_index=True, max_length=150),
        ),
    ]