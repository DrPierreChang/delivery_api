# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-07-31 08:48
from __future__ import unicode_literals

import django.contrib.postgres.fields.citext
from django.contrib.postgres.operations import CITextExtension
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0085_auto_20180706_2259'),
    ]

    operations = [
        CITextExtension(),
        migrations.AddField(
            model_name='merchant',
            name='call_center_email',
            field=django.contrib.postgres.fields.citext.CIEmailField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='merchant',
            name='low_feedback_value',
            field=models.PositiveIntegerField(default=3, help_text='Set the number of stars that should be considered as low rating'),
        ),
    ]
