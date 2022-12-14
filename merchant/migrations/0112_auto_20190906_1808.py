# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2019-09-06 08:08
from __future__ import unicode_literals

import django.contrib.postgres.fields
from django.db import migrations, models
from django.db.models import Q


def fill_webhook_url_list(apps, schema_editor):
    Merchant = apps.get_model('merchant', 'Merchant')
    for merchant in Merchant.objects.exclude(Q(webhook_url='') | Q(webhook_url__isnull=True)):
        merchant.webhook_url_list = [merchant.webhook_url]
        merchant.save(update_fields=('webhook_url_list', ))


def reverse_migration_code(apps, schema_editor):
    Merchant = apps.get_model('merchant', 'Merchant')
    for merchant in Merchant.objects.exclude(webhook_url_list=[]):
        merchant.webhook_url = merchant.webhook_url_list[0]
        merchant.save(update_fields=('webhook_url',))


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0111_merge_20190829_1747'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='webhook_url_list',
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(blank=True, null=True, max_length=200), default=list, size=5,
                blank=True),
        ),
        migrations.RunPython(fill_webhook_url_list, reverse_code=reverse_migration_code),
        migrations.RemoveField(
            model_name='merchant',
            name='webhook_url'
        ),
        migrations.RenameField(
            model_name='merchant',
            old_name='webhook_url_list',
            new_name='webhook_url'
        )
    ]
