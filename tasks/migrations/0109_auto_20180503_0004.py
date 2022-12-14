# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-05-02 14:04
from __future__ import unicode_literals

import json
import os

from django.db import migrations, models

from radaro_utils import helpers

dumps = 0


def load_dump(apps, schema_migration):
    global dumps
    ExternalJob = apps.get_model('tasks', 'ExternalJob')
    for d in range(dumps):
        with open('ext_jobs_dumps/dmp_{}.json'.format(d), 'rt') as f:
            dmp = json.load(f)
            for _id in dmp.keys():
                print('{} is not valid.\n-\nContent: {}\n============\n'.format(_id, json.dumps(dmp[_id])))
                ExternalJob.objects.filter(id=_id).update(content=json.dumps(dmp[_id]))


def save_dump(apps, schema_migration):
    global dumps
    if not os.path.exists('ext_jobs_dumps'):
        os.mkdir('ext_jobs_dumps')
    ExternalJob = apps.get_model('tasks', 'ExternalJob')
    ex_jobs = ExternalJob.objects.values_list('id', 'content')
    for chunk in helpers.chunks(ex_jobs, n=5000, length=ex_jobs.count()):
        dmp = {}
        for _id, _extra in chunk:
            if _extra:
                try:
                    val = json.loads(_extra)
                except ValueError:
                    dmp[_id] = eval(_extra)
            else:
                dmp[_id] = {}
        if dmp:
            with open('ext_jobs_dumps/dmp_{}.json'.format(dumps), 'wt') as f:
                json.dump(dmp, f)
            dumps += 1


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0108_auto_20180503_0001'),
    ]

    operations = [
        migrations.RenameField(
            model_name='externaljob',
            old_name='created_at',
            new_name='created',
        ),
        migrations.RenameField(
            model_name='externaljob',
            old_name='updated_at',
            new_name='modified',
        ),
        migrations.RunPython(code=save_dump, reverse_code=migrations.RunPython.noop),
        migrations.RunPython(code=load_dump, reverse_code=migrations.RunPython.noop),
        migrations.CreateModel(
            name='ExternalJobs',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.CharField(blank=True, max_length=250, null=True)),
                ('source_id', models.PositiveIntegerField(blank=True, null=True)),
                ('source_type', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE,
                                                  to='contenttypes.ContentType')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='externaljobs',
            unique_together=set([('source_type', 'source_id', 'external_id')]),
        ),
    ]
