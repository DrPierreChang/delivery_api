# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-12-28 11:50
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0048_auto_20181211_1915'),
    ]

    operations = [
        migrations.AlterField(
            model_name='templateemailattachment',
            name='email_message',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='notification.TemplateEmailMessage'),
        ),
    ]
