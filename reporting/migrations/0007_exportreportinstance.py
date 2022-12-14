# -*- coding: utf-8 -*-
# Generated by Django 1.9.3 on 2016-07-12 11:12
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion

import radaro_utils.files.utils


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0019_merge'),
        ('reporting', '0006_event_merchant'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExportReportInstance',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(null=True, upload_to=radaro_utils.files.utils.get_upload_path)),
                ('status', models.CharField(choices=[('failed', 'Failed'), ('in_progress', 'In progress'), ('completed', 'Completed')], default='in_progress', max_length=25)),
                ('comment', models.TextField(blank=True)),
                ('type', models.CharField(choices=[('r', 'Read'), ('w', 'Write')], default='r', max_length=2)),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='merchant.Merchant')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
