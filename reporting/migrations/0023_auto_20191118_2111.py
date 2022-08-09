# -*- coding: utf-8 -*-
# Generated by Django 1.11.25 on 2019-11-18 10:11
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0022_merge_20190206_0142'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='event',
            index=models.Index(fields=['merchant', 'created_at'], name='reporting_e_merchan_0f8862_idx'),
        ),
        migrations.AddIndex(
            model_name='event',
            index=models.Index(fields=['content_type', 'object_id'], name='reporting_e_content_58c7d7_idx'),
        ),
    ]