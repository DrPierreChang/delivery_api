# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-10-09 06:08
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [('merchant', '0056_auto_20170927_1806'), ('merchant', '0057_auto_20170928_2316'), ('merchant', '0057_auto_20171005_1742'), ('merchant', '0058_auto_20171006_1720')]

    dependencies = [
        ('merchant', '0034_auto_20161123_1935_squashed_0056_merge_20170921_1835'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='use_custom_phone_for_subbranding',
            field=models.BooleanField(default=False, help_text="Enables overriding merchant's phone by sub-brand."),
        ),
        migrations.AddField(
            model_name='subbranding',
            name='phone',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AlterModelOptions(
            name='subbranding',
            options={'ordering': ('name',), 'verbose_name': 'Sub-branding Merchant', 'verbose_name_plural': 'Sub-branding Merchants'},
        ),
        migrations.RenameField(
            model_name='subbranding',
            old_name='title',
            new_name='name',
        ),
    ]