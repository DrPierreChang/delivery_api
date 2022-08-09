# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-10-04 13:57
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('merchant', '0025_merchant_timezone'),
    ]

    operations = [
        migrations.CreateModel(
            name='RevelSystem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('api_key', models.CharField(max_length=50)),
                ('api_secret', models.CharField(max_length=100)),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='merchant.Merchant')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]