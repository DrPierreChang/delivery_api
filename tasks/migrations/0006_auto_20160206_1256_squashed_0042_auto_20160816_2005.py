# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-05-04 09:17
from __future__ import unicode_literals

import base.utils
from django.conf import settings
import django.contrib.postgres.fields
import django.core.validators
from django.db import migrations, models
import django.db.migrations.operations.special
import django.db.models.deletion
import location_field.models.plain

import radaro_utils.files.utils
import tasks.models.orders


# Functions from the following migrations need manual copying.
# Move them and any dependencies into this file, then update the
# RunPython operations to refer to the local versions:
# tasks.migrations.0014_order_manager
# tasks.migrations.0015_auto_20160309_0800
# tasks.migrations.0018_auto_20160317_1438
# tasks.migrations.0019_order_order_id
# tasks.migrations.0036_auto_20160520_2357

class Migration(migrations.Migration):

    replaces = [('tasks', '0006_auto_20160206_1256'), ('tasks', '0007_order_customer_token'), ('tasks', '0008_remove_customer_location'), ('tasks', '0009_auto_20160211_1205'), ('tasks', '0010_auto_20160212_0703'), ('tasks', '0011_auto_20160212_1048'), ('tasks', '0012_auto_20160219_1155'), ('tasks', '0013_auto_20160224_1840'), ('tasks', '0014_order_manager'), ('tasks', '0015_auto_20160309_0800'), ('tasks', '0016_auto_20160310_1440'), ('tasks', '0017_auto_20160317_1437'), ('tasks', '0018_auto_20160317_1438'), ('tasks', '0019_order_order_id'), ('tasks', '0020_auto_20160319_0638'), ('tasks', '0021_auto_20160321_1042'), ('tasks', '0022_order_confirmation'), ('tasks', '0023_order_path'), ('tasks', '0024_auto_20160325_1231'), ('tasks', '0025_auto_20160328_1406'), ('tasks', '0026_order_confirmation_signature'), ('tasks', '0027_order_start_address'), ('tasks', '0028_order_order_distance'), ('tasks', '0029_auto_20160413_1310'), ('tasks', '0030_auto_20160414_0713'), ('tasks', '0031_remove_order_start_address'), ('tasks', '0032_order_starting_point'), ('tasks', '0033_auto_20160513_2207'), ('tasks', '0034_order_external_job'), ('tasks', '0035_auto_20160517_1843'), ('tasks', '0036_auto_20160520_2357'), ('tasks', '0037_order_duration'), ('tasks', '0038_order_deadline_notified'), ('tasks', '0039_auto_20160712_2112'), ('tasks', '0040_auto_20160725_2020'), ('tasks', '0041_order_started_at'), ('tasks', '0042_auto_20160816_2005')]

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('merchant', '0003_auto_20160208_1407'),
        ('driver', '0001_initial'),
        ('tasks', '0001_squashed_0005_auto_20160205_1042'),
        ('webhooks', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='deliver_from',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='merchant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='merchant.Merchant'),
        ),
        migrations.AlterField(
            model_name='order',
            name='pickup_from',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(choices=[('failed', 'Failed'), ('rejected', 'Rejected'), ('created', 'Created'), ('assigned', 'Assigned'), ('in_progress', 'In progress'), ('delivered', 'Delivered'), ('confirmed', 'Confirmed')], default='created', max_length=20),
        ),
        migrations.AddField(
            model_name='order',
            name='order_token',
            field=models.CharField(blank=True, db_index=True, max_length=150),
        ),
        migrations.RemoveField(
            model_name='customer',
            name='location',
        ),
        migrations.AddField(
            model_name='order',
            name='title',
            field=models.CharField(default=None, max_length=100),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='order',
            name='deliver_address',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deliver', to='routing.Location'),
        ),
        migrations.AlterField(
            model_name='order',
            name='pickup_address',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pickup', to='routing.Location'),
        ),
        migrations.AddField(
            model_name='order',
            name='weight',
            field=models.CharField(choices=[('small', 'Small'), ('medium', 'Medium'), ('large', 'Large')], default='small', max_length=20),
        ),
        migrations.AlterField(
            model_name='customer',
            name='phone',
            field=models.CharField(max_length=40),
        ),
        migrations.CreateModel(
            name='BulkDelayedUpload',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('csv_file', models.FileField(upload_to=radaro_utils.files.utils.get_upload_path)),
                ('status', models.CharField(choices=[('failed', 'Failed'), ('created', 'Created'), ('in_progress', 'In progress'), ('completed', 'Completed')], default='created', max_length=25)),
                ('comment', models.TextField(blank=True)),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='merchant.Merchant')),
            ],
        ),
        migrations.AddField(
            model_name='order',
            name='bulk',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='orders', to='tasks.BulkDelayedUpload'),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(choices=[('failed', 'Failed'), ('terminated', 'Terminated'), ('not_assigned', 'Not assigned'), ('assigned', 'Assigned'), ('go_to_pick_up', 'Go to pick up'), ('picked_up', 'Picked up'), ('in_progress', 'In progress'), ('delivered', 'Delivered'), ('confirmed', 'Confirmed')], default='not_assigned', max_length=20),
        ),
        migrations.AddField(
            model_name='order',
            name='manager',
            field=models.ForeignKey(default=None, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='orders', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='order',
            name='manager',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='OrderLocation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('address', models.CharField(blank=True, max_length=255)),
                ('location', location_field.models.plain.PlainLocationField(default=None, max_length=63)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('description', models.CharField(blank=True, max_length=150)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AlterField(
            model_name='order',
            name='deliver_address',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deliver', to='tasks.OrderLocation'),
        ),
        migrations.AlterField(
            model_name='order',
            name='pickup_address',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pickup', to='tasks.OrderLocation'),
        ),
        migrations.RemoveField(
            model_name='order',
            name='deliver_from',
        ),
        migrations.RemoveField(
            model_name='order',
            name='pickup_before',
        ),
        migrations.RemoveField(
            model_name='order',
            name='pickup_from',
        ),
        migrations.AlterField(
            model_name='order',
            name='customer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tasks.Customer'),
        ),
        migrations.AddField(
            model_name='order',
            name='order_id',
            field=models.PositiveIntegerField(db_index=True, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='order_id',
            field=models.PositiveIntegerField(db_index=True, unique=True),
        ),
        migrations.RenameField(
            model_name='order',
            old_name='description',
            new_name='comment',
        ),
        migrations.RemoveField(
            model_name='customer',
            name='description',
        ),
        migrations.AlterField(
            model_name='order',
            name='pickup_address',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='pickup', to='tasks.OrderLocation'),
        ),
        migrations.AddField(
            model_name='order',
            name='confirmation_photo',
            field=models.ImageField(blank=True, null=True, upload_to=radaro_utils.files.utils.get_upload_path),
        ),
        migrations.AddField(
            model_name='order',
            name='path',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=200), blank=True, null=True, size=None),
        ),
        migrations.AddField(
            model_name='order',
            name='customer_comment',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='rating',
            field=models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10)]),
        ),
        migrations.AddField(
            model_name='order',
            name='confirmation_comment',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='confirmation_signature',
            field=models.ImageField(blank=True, null=True, upload_to=radaro_utils.files.utils.get_upload_path),
        ),
        migrations.AddField(
            model_name='order',
            name='order_distance',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='customer',
            name='phone',
            field=models.CharField(max_length=40, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='deliver_before',
            field=models.DateTimeField(default=tasks.models.orders.order_deadline),
        ),
        migrations.AlterField(
            model_name='customer',
            name='email',
            field=models.EmailField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='customer',
            name='phone',
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='starting_point',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='starting', to='tasks.OrderLocation'),
        ),
        migrations.AlterField(
            model_name='order',
            name='title',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='order',
            name='external_job',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='order', to='webhooks.ExternalJob'),
        ),
        migrations.AddField(
            model_name='order',
            name='duration',
            field=models.DurationField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='deadline_notified',
            field=models.BooleanField(default=False),
        ),
        migrations.RemoveField(
            model_name='bulkdelayedupload',
            name='csv_file',
        ),
        migrations.AddField(
            model_name='bulkdelayedupload',
            name='file',
            field=models.FileField(null=True, upload_to=radaro_utils.files.utils.delayed_task_upload),
        ),
        migrations.AddField(
            model_name='bulkdelayedupload',
            name='type',
            field=models.CharField(choices=[('r', 'Read'), ('w', 'Write')], default='r', max_length=2),
        ),
        migrations.AlterField(
            model_name='bulkdelayedupload',
            name='status',
            field=models.CharField(choices=[('failed', 'Failed'), ('in_progress', 'In progress'), ('completed', 'Completed')], default='in_progress', max_length=25),
        ),
        migrations.AddField(
            model_name='order',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(choices=[('failed', 'Failed'), ('terminated', 'Terminated'), ('not_assigned', 'Not assigned'), ('assigned', 'Assigned'), ('go_to_pick_up', 'Go to pick up'), ('picked_up', 'Picked up'), ('in_progress', 'In progress'), ('delivered', 'Completed'), ('confirmed', 'Confirmed')], default='not_assigned', max_length=20),
        ),
    ]
