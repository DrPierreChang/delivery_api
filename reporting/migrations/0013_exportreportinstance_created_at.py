# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-05-22 13:19
from __future__ import unicode_literals

import datetime
from django.db import migrations, models
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0012_merge_20170517_1814'),
    ]

    operations = [
        migrations.AddField(
            model_name='exportreportinstance',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=datetime.datetime(2017, 5, 22, 13, 19, 16, 412629, tzinfo=utc)),
            preserve_default=False,
        ),
    ]
