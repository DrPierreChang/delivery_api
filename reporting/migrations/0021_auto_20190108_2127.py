# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2019-01-08 10:27
from __future__ import unicode_literals

from django.db import migrations
import radaro_utils.fields
import radaro_utils.files.utils


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0020_auto_20180904_2150'),
    ]

    operations = [
        migrations.AlterField(
            model_name='exportreportinstance',
            name='file',
            field=radaro_utils.fields.CustomFileField(null=True, upload_to=radaro_utils.files.utils.delayed_task_upload),
        ),
    ]
