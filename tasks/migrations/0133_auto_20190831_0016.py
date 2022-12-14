# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-08-30 14:16
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0112_merge_20190830_1846'),
        ('tasks', '0132_merge_20190830_1846'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='wayback_hub',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='wayback', to='merchant.Hub'),
        ),
        migrations.AddField(
            model_name='order',
            name='wayback_point',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='wayback', to='tasks.OrderLocation'),
        ),
    ]
