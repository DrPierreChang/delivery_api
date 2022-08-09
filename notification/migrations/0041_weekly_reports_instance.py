# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.template.loader import get_template

from notification.mixins import MessageTemplateStatus


def add_weekly_reports_object(apps, schema_migration):
    MerchantMessageTemplate = apps.get_model('notification', 'MerchantMessageTemplate')
    template_type = MessageTemplateStatus.WEEKLY_REPORT
    template_name = MessageTemplateStatus.template_names_map.get(template_type)
    text = get_template(template_name + '.txt').template.source
    html_text = get_template(template_name + '.html').template.source
    subject = get_template(template_name + '.subject').template.source

    MerchantMessageTemplate.objects.create(template_type=template_type, text=text, html_text=html_text,
                                           subject=subject, enabled=False, merchant=None)


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0040_auto_20181002_2015'),
    ]

    operations = [
        migrations.RunPython(code=add_weekly_reports_object, reverse_code=migrations.RunPython.noop),
    ]
