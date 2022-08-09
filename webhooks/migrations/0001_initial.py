# -*- coding: utf-8 -*-
# Generated by Django 1.9.3 on 2016-05-16 11:12
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('merchant', '0015_merchant_country'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExternalJob',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('extra', models.TextField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='MerchantAPIKey',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('available', models.BooleanField(default=True)),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='merchant_tokens', to='merchant.Merchant')),
            ],
        ),
        migrations.CreateModel(
            name='MerchantAPIKeyEvents',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.CharField(max_length=120)),
                ('user_agent', models.CharField(max_length=250)),
                ('happened_at', models.DateTimeField(auto_now_add=True)),
                ('event_type', models.IntegerField(choices=[(1, 'Created'), (0, 'Used'), (-1, 'Deleted'), (2, 'Changed')], default=1)),
                ('field', models.CharField(blank=True, max_length=45, null=True)),
                ('new_value', models.CharField(blank=True, max_length=256, null=True)),
                ('merchant_api_key', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='api_key_events', to='webhooks.MerchantAPIKey')),
            ],
        ),
        migrations.AddField(
            model_name='externaljob',
            name='api_key',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='external_jobs', to='webhooks.MerchantAPIKey'),
        ),
        migrations.AlterUniqueTogether(
            name='externaljob',
            unique_together=set([('external_id', 'api_key')]),
        ),
    ]
