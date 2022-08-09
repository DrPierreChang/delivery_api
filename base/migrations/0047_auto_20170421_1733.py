# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-04-21 07:33
from __future__ import unicode_literals

import base.models.members
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0046_auto_20170411_0208'),
    ]

    operations = [
        migrations.AlterModelManagers(
            name='member',
            managers=[
                ('objects', models.Manager()),
                ('drivers', base.models.members.ActiveDriversManager()),
                ('all_drivers', base.models.members.DriversManager()),
                ('managers', base.models.members.ManagersManager()),
            ],
        ),
    ]