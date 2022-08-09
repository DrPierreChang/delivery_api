# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2019-01-25 13:39
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('merchant', '0098_auto_20190124_0033'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='driverhub',
            unique_together=set([('hub', 'driver')]),
        ),
    ]