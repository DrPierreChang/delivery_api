# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2019-01-14 08:33
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant_extension', '0004_auto_20190110_2200'),
    ]

    operations = [
        migrations.AddField(
            model_name='resultchecklist',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
    ]