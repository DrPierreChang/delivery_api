# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-09-04 11:50
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reporting', '0019_auto_20180713_0057'),
    ]

    operations = [
        migrations.AddField(
            model_name='exportreportinstance',
            name='initiator',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='exportreportinstance',
            name='merchant',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='merchant.Merchant'),
        ),
    ]
