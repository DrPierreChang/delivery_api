# Generated by Django 2.2.5 on 2020-09-08 10:15

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0150_auto_20200807_0035'),
    ]

    operations = [
        migrations.AddField(
            model_name='skid',
            name='driver_changes',
            field=models.CharField(blank=True, choices=[('added', 'Added'), ('edited', 'Edited'), ('deleted', 'Deleted')], default=None, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='skid',
            name='original_skid',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=None, null=True),
        ),
    ]
