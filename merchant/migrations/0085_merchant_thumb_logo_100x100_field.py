# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-08-15 12:22
from __future__ import unicode_literals

import base.utils
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0084_merchant_feedback_redirect_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='thumb_logo_100x100_field',
            field=models.ImageField(blank=True, null=True, upload_to=base.utils.ThumbnailsUploadPath()),
        ),
    ]
