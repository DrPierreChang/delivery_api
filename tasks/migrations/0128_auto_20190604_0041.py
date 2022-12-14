# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-06-03 14:41
from __future__ import unicode_literals

from django.db import migrations


def fill_labels_field(apps, schema_editor):
    Order = apps.get_model('tasks', 'Order')
    ThroughModel = Order.labels.through
    print('start: %s' % Order.objects.filter(label__isnull=False).count())
    while Order.objects.filter(label__isnull=False).exists():
        print('exists: %s' % Order.objects.filter(label__isnull=False).count())
        orders = Order.objects.filter(label__isnull=False)[:1000]
        for_save = [ThroughModel(order_id=order.id, label_id=order.label_id) for order in orders]
        ThroughModel.objects.bulk_create(for_save)
        Order.objects.filter(id__in=orders.values_list('id', flat=True)).update(label=None)
    print('left: %s' % Order.objects.filter(label__isnull=False).count())


def fill_label_field_back(apps, schema_editor):
    Order = apps.get_model('tasks', 'Order')
    for order in Order.objects.filter(labels__isnull=False):
        order.label = order.labels.first()
        order.save()


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0127_auto_20190603_2344'),
    ]

    operations = [
        migrations.RunPython(fill_labels_field, fill_label_field_back),
    ]
