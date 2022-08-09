# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2019-11-16 10:13
from __future__ import unicode_literals

from django.db import migrations, models
from django.db.models import Case, When, Value
from merchant.models.merchant import Merchant as MerchantModel


def set_option_barcodes(apps, schema_editor):
    Merchant = apps.get_model('merchant', 'Merchant')
    Merchant.objects.update(
       option_barcodes=Case(
          When(enable_barcodes=True,
               then=Value(MerchantModel.TYPES_BARCODES.before)
               ), default=Value(MerchantModel.TYPES_BARCODES.disable)
        )
    )


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0116_remove_merchant_driver_jobs_ordering'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='option_barcodes',
            field=models.CharField(choices=[('disable', 'Disable'), ('before', 'Scan at the warehouse'), ('after', 'Scan upon delivery'), ('both', 'Scan both times')], default='disable', max_length=8, verbose_name='Barcodes'),
        ),
        migrations.RunPython(code=set_option_barcodes, reverse_code=migrations.RunPython.noop),
    ]
