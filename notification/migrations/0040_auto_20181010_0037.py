# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-10-09 13:37
from __future__ import unicode_literals

from django.db import migrations, models
from django.template.loader import get_template

from notification.mixins import MessageTemplateStatus


def add_advanced_completion_template(apps, schema_editor):
    Merchant = apps.get_model('merchant', 'Merchant')
    MerchantMessageTemplate = apps.get_model('notification', 'MerchantMessageTemplate')

    def templates_generator():
        template_type = MessageTemplateStatus.ADVANCED_COMPLETION
        template_name = MessageTemplateStatus.template_names_map.get(template_type)
        text = get_template(template_name + '.txt').template.source
        html_text = get_template(template_name + '.html').template.source
        subject = get_template(template_name + '.subject').template.source
        for merchant in Merchant.objects.exclude(templates__template_type=template_type):
            yield MerchantMessageTemplate(
                template_type=template_type, text=text,
                html_text=html_text, subject=subject,
                enabled=True, merchant=merchant
            )
    MerchantMessageTemplate.objects.bulk_create(templates_generator())


def reverse_migration(apps, schema_editor):
    MerchantMessageTemplate = apps.get_model('notification', 'MerchantMessageTemplate')
    template_type = MessageTemplateStatus.ADVANCED_COMPLETION
    MerchantMessageTemplate.objects.filter(template_type=template_type).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0039_auto_20180928_2048'),
    ]

    operations = [
        migrations.AlterField(
            model_name='merchantmessagetemplate',
            name='template_type',
            field=models.IntegerField(choices=[(0, 'Another'), (1, 'Customer job started'), (2, 'Customer job terminated'), (3, 'Reminder (1h)'), (4, 'Reminder (24h)'), (5, 'Driver job started'), (6, 'Complete invitation'), (7, 'Invitation'), (8, 'Confirm account'), (9, 'Reset password'), (10, 'Billing'), (11, 'Account locked'), (12, 'Low customer feedback'), (13, 'Upcoming delivery'), (15, 'Advanced completion')], default=0),
        ),
        migrations.RunPython(add_advanced_completion_template, reverse_code=reverse_migration)
    ]
