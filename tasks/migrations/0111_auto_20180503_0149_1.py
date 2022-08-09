# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-05-02 15:49
from __future__ import unicode_literals


from bulk_update.helper import bulk_update
from django.db import migrations

from radaro_utils import helpers


CHUNK_SIZE = 3000


# Creating new ExternalJob models in chunks
def migrate_sources(apps, schema_migration):
    # Migrate done external jobs
    OrderPrototype = apps.get_model('tasks', 'OrderPrototype')
    ExternalJob = apps.get_model('tasks', 'ExternalJob')
    prots = OrderPrototype.objects.all()
    a = 0
    print('{} lines.'.format(prots.count() / CHUNK_SIZE))
    for ch in helpers.chunks(prots.order_by('id'), n=CHUNK_SIZE, length=prots.count()):
        _ch = list(ch)
        ext_jobs = ExternalJob.objects.bulk_create(
            ExternalJob(source_id=o.source_id,
                        source_type_id=o.source_type_id,
                        external_id=o.external_id)
            for o in ch
        )
        for p, ext_job in zip(_ch, ext_jobs):
            p.external_job = ext_job
        bulk_update(_ch, update_fields=['external_job'])
        a += 1
        print('Saved {} line.'.format(a))
    null_exists = prots.filter(external_job__isnull=True).count()
    assert null_exists == 0, 'Exists {} nulls in OrderPrototype.external_job'.format(null_exists)


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('tasks', '0110_auto_20180503_0031'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ExternalJobs',
            new_name='ExternalJob',
        ),
        migrations.RunPython(code=migrate_sources, reverse_code=migrations.RunPython.noop),
    ]