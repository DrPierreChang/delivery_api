# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-04-14 07:03
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('webhooks', '0005_auto_20161117_0022'),
    ]

    operations = [
        migrations.AlterField(
            model_name='merchantapikeyevents',
            name='merchant_api_key',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='api_key_events', to='webhooks.MerchantAPIKey'),
        ),
    ]