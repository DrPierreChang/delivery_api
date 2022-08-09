# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-05-04 09:36
from __future__ import unicode_literals

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import jsonfield.fields


class Migration(migrations.Migration):

    replaces = [('tasks', '0043_order_deleted'), ('tasks', '0044_bulkdelayedupload_data'), ('tasks', '0045_auto_20160905_2346'), ('tasks', '0044_order_updated_at'), ('tasks', '0046_merge'), ('tasks', '0046_auto_20160912_1738'), ('tasks', '0045_auto_20160913_1940'), ('tasks', '0047_merge'), ('tasks', '0048_auto_20160913_2109'), ('tasks', '0049_auto_20160914_2046'), ('tasks', '0050_auto_20160914_2048'), ('tasks', '0051_order_created_at'), ('tasks', '0052_auto_20160916_2153'), ('tasks', '0053_order_deadline_passed'), ('tasks', '0054_auto_20160923_2245'), ('tasks', '0048_bulkdelayedupload_saved'), ('tasks', '0053_merge'), ('tasks', '0055_merge')]

    dependencies = [
        ('tasks', '0006_auto_20160206_1256_squashed_0042_auto_20160816_2005'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='bulkdelayedupload',
            name='data',
            field=jsonfield.fields.JSONField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(choices=[('not_assigned', 'Not assigned'), ('assigned', 'Assigned'), ('go_to_pick_up', 'Go to pick up'), ('picked_up', 'Picked up'), ('in_progress', 'In progress'), ('terminated', 'Terminated'), ('delivered', 'Completed'), ('confirmed', 'Confirmed'), ('failed', 'Failed')], default='not_assigned', max_length=20),
        ),
        migrations.AddField(
            model_name='order',
            name='updated_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='customer',
            name='name',
            field=models.CharField(max_length=150, validators=[django.core.validators.RegexValidator(message="Name cannot contain symbols different from latin letters, ', . and -.", regex=b"^[a-zA-Z'\\.\\-][a-zA-Z-' \\.\\-]+$")]),
        ),
        migrations.AlterField(
            model_name='customer',
            name='name',
            field=models.CharField(max_length=150, validators=[django.core.validators.RegexValidator(message="Name cannot contain symbols different from latin letters, ', . and -.", regex=b"^[a-zA-Z'\\.\\-][a-zA-Z-' \\.\\-]+$")]),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(choices=[('not_assigned', 'Not assigned'), ('assigned', 'Assigned'), ('go_to_pick_up', 'Go to pick up'), ('picked_up', 'Picked up'), ('in_progress', 'In progress'), ('terminated', 'Terminated'), ('delivered', 'Completed'), ('confirmed', 'Confirmed'), ('failed', 'Failed')], default='not_assigned', max_length=20),
        ),
        migrations.AlterField(
            model_name='order',
            name='customer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to='tasks.Customer'),
        ),
        migrations.AddField(
            model_name='order',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AddField(
            model_name='order',
            name='deadline_passed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='bulkdelayedupload',
            name='saved',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
