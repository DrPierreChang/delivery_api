# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.template.loader import get_template

from notification.mixins import MessageTemplateStatus


def add_upcoming_delivery_migration(apps, schema_editor):
    Merchant = apps.get_model('merchant', 'Merchant')
    MerchantMessageTemplate = apps.get_model('notification', 'MerchantMessageTemplate')

    template_type = MessageTemplateStatus.UPCOMING_DELIVERY
    template_name = MessageTemplateStatus.template_names_map.get(template_type)
    text = get_template(template_name + '.txt').template.source
    html_text = get_template(template_name + '.html').template.source
    subject = get_template(template_name + '.subject').template.source

    for merchant in Merchant.objects.exclude(templates__template_type=template_type):
        MerchantMessageTemplate.objects.create(template_type=template_type, text=text, html_text=html_text,
                                               subject=subject, enabled=False, merchant=merchant)


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0033_auto_20180709_1636'),
        ('merchant', '0086_merchant_delivery_interval'),
    ]

    operations = [
        migrations.RunPython(add_upcoming_delivery_migration, reverse_code=migrations.RunPython.noop)
    ]
