# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2019-06-11 07:27
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0106_merge_20190521_2122'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='customer_review_opt_in_enabled',
            field=models.BooleanField(default=False, verbose_name='Enable customer review opt-in'),
        ),
        migrations.AddField(
            model_name='merchant',
            name='customer_review_opt_in_text',
            field=models.TextField(default='Tap here to allow us to publicly share your feedback.',
                                   verbose_name='Customer review opt-in text'),
        ),
    ]