# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-07-09 06:36
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0032_auto_20180606_1958'),
    ]

    operations = [
        migrations.AlterField(
            model_name='merchantmessagetemplate',
            name='template_type',
            field=models.IntegerField(choices=[(0, 'Another'), (1, 'Customer job started'), (2, 'Customer job terminated'), (3, 'Follow up'), (4, 'Follow up reminder'), (5, 'Driver job started'), (6, 'Complete invitation'), (7, 'invitation'), (8, 'Confirm account'), (9, 'Reset password'), (10, 'Billing'), (11, 'Account locked'), (13, 'Upcoming delivery')], default=0),
        ),
    ]