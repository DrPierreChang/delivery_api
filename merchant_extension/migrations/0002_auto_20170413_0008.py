# -*- coding: utf-8 -*-
# Generated by Django 1.9.11 on 2017-04-12 14:08
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('merchant_extension', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='question',
            unique_together=set([]),
        ),
    ]
