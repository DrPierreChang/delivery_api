# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-05-30 12:05
from __future__ import unicode_literals

import copy

from django.db import migrations
from django.template.loader import get_template

from notification.mixins import MessageTemplateStatus as Status


# noinspection PyCompatibility
def create_merchant_message_templates(apps, schema_editor):
    Merchant = apps.get_model('merchant', 'Merchant')
    MerchantMessageTemplate = apps.get_model('notification', 'MerchantMessageTemplate')

    customizable_templates_map = {
        Status.CUSTOMER_JOB_STARTED: ['sms_template', 'sms_enable'],
        Status.CUSTOMER_JOB_TERMINATED: ['job_termination_sms_template', 'job_termination_sms_enable'],
        Status.FOLLOW_UP: ['first_reminder_sms_template', 'send_first_reminder'],
        Status.FOLLOW_UP_REMINDER: ['follow_up_reminder_sms_template', 'follow_up_reminder']
    }

    msg_templates = []

    file_name = Status.template_names_map.get(Status.ANOTHER)
    text = get_template(file_name + '.txt').template.source
    another_msg_template = MerchantMessageTemplate(text=text, template_type=Status.ANOTHER)
    msg_templates.append(another_msg_template)

    merchant_templates_map = copy.copy(Status.template_names_map)
    # del merchant_templates_map[Status.ANOTHER]

    for merchant in Merchant.objects.all():
        for template_type, template_name in merchant_templates_map.items():
            enabled = True
            use_default = True

            if template_type in customizable_templates_map:
                use_default = False
                text_field_name, enabled_field = customizable_templates_map.get(template_type)
                text, enabled = getattr(merchant, text_field_name), getattr(merchant, enabled_field)
            else:
                text = get_template(template_name + '.txt').template.source
            html_text = get_template(template_name + '.html').template.source
            subject = get_template(template_name + '.subject').template.source

            msg_templates.append(MerchantMessageTemplate(template_type=template_type, text=text, html_text=html_text,
                                                         subject=subject, enabled=enabled,
                                                         merchant=merchant, use_default=use_default))

    MerchantMessageTemplate.objects.bulk_create(msg_templates)


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0029_auto_20180530_2204'),
    ]

    operations = [
        migrations.RunPython(code=create_merchant_message_templates, reverse_code=migrations.RunPython.noop)
    ]
