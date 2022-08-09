# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-10-15 11:43
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0041_merge_20181015_2242'),
    ]

    operations = [
        migrations.AlterField(
            model_name='merchantmessagetemplate',
            name='template_type',
            field=models.IntegerField(choices=[(0, 'Another'), (1, 'Customer job started'), (2, 'Customer job terminated'), (3, 'Reminder (1h)'), (4, 'Reminder (24h)'), (5, 'Driver job started'), (6, 'Complete invitation'), (7, 'Invitation'), (8, 'Confirm account'), (9, 'Reset password'), (10, 'Billing'), (11, 'Account locked'), (12, 'Low customer feedback'), (13, 'Upcoming delivery')], default=0),
        ),
    ]