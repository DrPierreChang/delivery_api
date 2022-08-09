# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-05-02 14:01
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone
import jsonfield.fields
import model_utils.fields


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0107_merge_20180322_1914'),
    ]

    operations = [
        migrations.AddField(
            model_name='externaljob',
            name='bulk',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='tasks.BulkDelayedUpload', related_name='prototypes'),
        ),
        migrations.AlterField(
            model_name='bulkdelayedupload',
            name='method',
            field=models.CharField(choices=[('web', 'WEB'), ('api', 'API'), ('external', 'External API'), ('no_info', 'No info')], default='no_info', max_length=10),
        ),
        migrations.AlterField(
            model_name='externaljob',
            name='created_at',
            field=model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created'),
        ),
        migrations.RenameField(
            model_name='externaljob',
            old_name='extra',
            new_name='content',
        ),
        migrations.AlterField(
            model_name='externaljob',
            name='updated_at',
            field=model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified'),
        ),
        migrations.AlterField(
            model_name='order',
            name='serialized_track',
            field=jsonfield.fields.JSONField(default=list),
        ),
    ]
