# Generated by Django 2.2.5 on 2020-09-18 11:13

from django.db import migrations, models
from django.template.loader import get_template

from notification.mixins import MessageTemplateStatus


def create_upcoming_ro_templates(apps, schema_editor):
    Merchant = apps.get_model('merchant', 'Merchant')
    MerchantMessageTemplate = apps.get_model('notification', 'MerchantMessageTemplate')

    def templates_generator():
        template_type = MessageTemplateStatus.RO_UPCOMING_DELIVERY
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


def remove_upcoming_ro_templates(apps, schema_editor):
    MerchantMessageTemplate = apps.get_model('notification', 'MerchantMessageTemplate')
    template_type = MessageTemplateStatus.RO_UPCOMING_DELIVERY
    MerchantMessageTemplate.objects.filter(template_type=template_type).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0055_auto_20200408_2342'),
    ]

    operations = [
        migrations.AlterField(
            model_name='merchantmessagetemplate',
            name='template_type',
            field=models.IntegerField(choices=[(0, 'Another'), (1, 'Customer job started'), (2, 'Customer job terminated'), (3, 'Reminder (1h)'), (4, 'Reminder (24h)'), (5, 'Driver job started'), (6, 'Complete invitation'), (7, 'Invitation'), (8, 'Confirm account'), (9, 'Reset password'), (10, 'Billing'), (11, 'Account locked'), (12, 'Low customer feedback'), (13, 'Upcoming delivery'), (19, 'Instant upcoming delivery'), (14, 'Weekly Radaro usage report'), (15, 'Advanced completion'), (16, 'Jobs daily report'), (17, 'Proof of delivery report'), (18, 'Start of Day checklist answer issue'), (20, 'Miele customer survey'), (21, 'Survey report'), (22, 'Upcoming pick up'), (23, 'Route optimisation upcoming delivery')], default=0),
        ),
        migrations.RunPython(create_upcoming_ro_templates, reverse_code=remove_upcoming_ro_templates),
    ]
