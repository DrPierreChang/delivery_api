# -*- coding: utf-8 -*-
# Generated by Django 1.10.3 on 2016-11-21 07:42
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0033_auto_20161117_2327'),
        ('tasks', '0058_auto_20161117_2014'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='merchant',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, to='merchant.Merchant'),
        )
    ]
