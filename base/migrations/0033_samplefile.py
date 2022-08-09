# -*- coding: utf-8 -*-
# Generated by Django 1.9.3 on 2016-08-26 09:06
from __future__ import unicode_literals

import base.utils
from django.db import migrations, models

import radaro_utils.files.utils


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0032_auto_20160824_2134'),
    ]

    operations = [
        migrations.CreateModel(
            name='SampleFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to=radaro_utils.files.utils.get_upload_path)),
                ('name', models.CharField(blank=True, max_length=256)),
                ('category', models.CharField(choices=[('csv_import', 'CSV Import Example')], max_length=256)),
                ('comment', models.TextField(blank=True)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('changed_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]