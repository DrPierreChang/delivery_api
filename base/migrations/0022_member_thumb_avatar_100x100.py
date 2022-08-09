# -*- coding: utf-8 -*-
# Generated by Django 1.9.3 on 2016-03-17 11:44
from __future__ import unicode_literals

import base.utils
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0021_auto_20160309_1147'),
    ]

    operations = [
        migrations.AddField(
            model_name='member',
            name='thumb_avatar_100x100',
            field=models.ImageField(blank=True, null=True, upload_to=base.utils.get_upload_path_100x100),
        ),
    ]
