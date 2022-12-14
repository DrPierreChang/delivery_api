# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-05-08 14:56
from __future__ import unicode_literals

import operator

from django.db import migrations, models, connection

from radaro_utils import compat


# Fast setting external_job_id from corresponding prototypes to orders
def migrate(apps, schema_migration):
    OrderPrototype = apps.get_model('tasks', 'OrderPrototype')
    with connection.cursor() as cursor:
        cursor.execute('UPDATE tasks_order t SET external_job_id = p.external_job_id '
                       'FROM tasks_orderprototype p WHERE t.model_prototype_id = p.id')
    null_exists = OrderPrototype.objects.filter(external_job__isnull=True).count()
    assert null_exists == 0, 'Exists {} nulls in OrderPrototype.external_job'.format(null_exists)


def migrate_sources_back(apps, schema_migration):
    OrderPrototype = apps.get_model('tasks', 'OrderPrototype')
    with connection.cursor() as cursor:
        cursor.execute('UPDATE tasks_orderprototype p SET (source_id, source_type_id, external_id) = '
                       '(e.source_id, e.source_type_id, e.external_id) '
                       'FROM tasks_externaljob e WHERE p.external_job_id = e.id')

    upd_fields = ['source_id', 'source_type_id', 'external_id']
    null_test = (models.Q(**{k + '__isnull': True}) for k in upd_fields)
    null_exists = OrderPrototype.objects.filter(compat.reduce(operator.or_, null_test)).count()
    assert null_exists == 0, 'Exists {} nulls'.format(null_exists)


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0111_auto_20180503_0149_1'),
    ]

    operations = [
        migrations.RunPython(code=migrate, reverse_code=migrate_sources_back)
    ]
