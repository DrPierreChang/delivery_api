# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-06-30 14:02
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0048_auto_20170626_2011'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invite',
            name='pin_code',
            field=models.CharField(blank=True, db_index=True, max_length=20),
        ),
    ]