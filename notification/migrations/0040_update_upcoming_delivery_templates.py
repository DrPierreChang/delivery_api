# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from notification.mixins import MessageTemplateStatus


def update_upcoming_delivery_migration(apps, schema_editor):
    MerchantMessageTemplate = apps.get_model('notification', 'MerchantMessageTemplate')

    for template in MerchantMessageTemplate.objects.filter(template_type=MessageTemplateStatus.UPCOMING_DELIVERY):
        template.text = template.text.replace('{{welcome_text}} ', '{{welcome_text}}')
        template.save()


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0039_auto_20180928_2048'),
    ]

    operations = [
        migrations.RunPython(update_upcoming_delivery_migration, reverse_code=migrations.RunPython.noop)
    ]
