# -*- coding: utf-8 -*-
# Generated by Django 1.9.3 on 2016-05-16 08:26
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0023_remove_member_thumb_avatar_100x100'),
    ]

    operations = [
        migrations.AlterField(
            model_name='car',
            name='car_type',
            field=models.IntegerField(choices=[(0, 'Ute'), (1, 'Scooter'), (2, 'Car'), (3, 'Van'), (4, 'Truck')], default=2),
        ),
    ]