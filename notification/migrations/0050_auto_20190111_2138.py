# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2019-01-11 10:38
from __future__ import unicode_literals

from django.db import migrations
from django.template.loader import get_template

from notification.mixins import MessageTemplateStatus


def create_start_of_day_templates(apps, schema_editor):
    Merchant = apps.get_model('merchant', 'Merchant')
    MerchantMessageTemplate = apps.get_model('notification', 'MerchantMessageTemplate')

    def templates_generator():
        template_type = MessageTemplateStatus.SOD_ISSUE
        template_name = MessageTemplateStatus.template_names_map.get(template_type)
        text = get_template(template_name + '.txt').template.source
        html_text = get_template(template_name + '.html').template.source
        subject = get_template(template_name + '.subject').template.source
        for merchant in Merchant.objects.exclude(templates__template_type=template_type):
            yield MerchantMessageTemplate(
                template_type=template_type, text=text,
                html_text=html_text, subject=subject,
                enabled=False, merchant=merchant
            )

    MerchantMessageTemplate.objects.bulk_create(templates_generator())


def delete_start_of_day_templates(apps, schema_editor):
    MerchantMessageTemplate = apps.get_model('notification', 'MerchantMessageTemplate')

    template_type = MessageTemplateStatus.SOD_ISSUE

    MerchantMessageTemplate.objects.filter(template_type=template_type).delete()




class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0049_auto_20190111_2138'),
    ]

    operations = [
        migrations.RunPython(create_start_of_day_templates, reverse_code=delete_start_of_day_templates)
    ]
