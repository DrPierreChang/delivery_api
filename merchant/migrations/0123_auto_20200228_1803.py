# Generated by Django 2.2.5 on 2020-02-28 07:03

import django.contrib.postgres.fields.jsonb
from django.db import migrations
import merchant.models.merchant


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0122_auto_20200214_2157'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='assigned_job_screen_text',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=merchant.models.merchant.default_assigned_job_screen_text_dict, verbose_name='Customer tracking screen text about job assigned to the driver'),
        ),
        migrations.AddField(
            model_name='merchant',
            name='not_assigned_job_screen_text',
            field=django.contrib.postgres.fields.jsonb.JSONField(default=merchant.models.merchant.default_not_assigned_job_screen_text_dict, verbose_name='Customer tracking screen text about job creation'),
        ),
    ]
