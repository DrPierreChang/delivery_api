# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-06-15 08:15
from __future__ import unicode_literals

from django.db import migrations
from django.db.models import Q


def migrate_advanced_completion_setting(apps, schema_editor):
    Merchant = apps.get_model('merchant', 'Merchant')

    Merchant.objects.filter(use_success_codes=True).update(advanced_completion='optional')


def reverse_migration(apps, schema_editor):
    Merchant = apps.get_model('merchant', 'Merchant')

    Merchant.objects.filter(Q(advanced_completion='optional') | Q(advanced_completion='required'))\
        .update(use_success_codes=True)


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0080_merchant_advanced_completion'),
    ]

    operations = [
        migrations.RunPython(code=migrate_advanced_completion_setting, reverse_code=reverse_migration),
        migrations.RemoveField(model_name='merchant', name='use_success_codes')
    ]