# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-04-14 07:03
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('reporting', '0010_auto_20170104_2248'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='initiator',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='event',
            name='merchant',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='merchant.Merchant'),
        ),
        migrations.AlterField(
            model_name='exportreportinstance',
            name='merchant',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='merchant.Merchant'),
        ),
    ]
