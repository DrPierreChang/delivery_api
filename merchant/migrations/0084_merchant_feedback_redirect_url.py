# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-08-06 07:46
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0083_merge_20180627_2213'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='feedback_redirect_url',
            field=models.URLField(blank=True),
        ),
    ]
