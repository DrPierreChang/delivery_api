# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-09-26 13:35
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0034_auto_20161123_1935_squashed_0056_merge_20170921_1835'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='use_hubs',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='merchant',
            name='use_way_back_status',
            field=models.BooleanField(default=False, help_text='Available only with "use_hubs" setting.'),
        ),
    ]
