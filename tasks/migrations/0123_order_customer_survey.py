# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2019-04-04 09:40
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('merchant_extension', '0011_auto_20190320_2321'),
        ('tasks', '0122_merge_20181117_0121'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='customer_survey',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='customer_order', to='merchant_extension.SurveyResult'),
        ),
    ]
