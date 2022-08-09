# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-11-08 13:16
from __future__ import unicode_literals

from django.db import migrations, models


def migrate_terminate_codes(apps, schema_editor):
    Order = apps.get_model('tasks', 'Order')

    for order in Order.objects.filter(terminate_code__isnull=False):
        order.terminate_codes.add(order.terminate_code)


def reverse_migration(apps, schema_editor):
    Order = apps.get_model('tasks', 'Order')

    for order in Order.objects.filter(terminate_codes__isnull=False):
        order.terminate_code = order.terminate_codes.first()
        order.save(update_fields=('terminate_code', ))


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0110_terminatecode_email_notification_recipient'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='terminate_codes',
            field=models.ManyToManyField(to='tasks.TerminateCode', related_name='orders', blank=True)
        ),
        migrations.RunPython(code=migrate_terminate_codes, reverse_code=reverse_migration)
    ]