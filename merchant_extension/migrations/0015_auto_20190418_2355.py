# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2019-04-18 13:55
from __future__ import unicode_literals

from django.db import migrations, models
import merchant_extension.models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant_extension', '0014_auto_20190416_1824'),
    ]

    operations = [
        migrations.AddField(
            model_name='checklist',
            name='invite_text',
            field=models.TextField(blank=True, default=merchant_extension.models.get_checklist_default_invite_text),
        ),
        migrations.AddField(
            model_name='checklist',
            name='thanks_text',
            field=models.TextField(blank=True, default=merchant_extension.models.get_checklist_default_invite_text),
        ),
    ]
