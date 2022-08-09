# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-02-29 10:36
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0014_auto_20160218_1410'),
    ]

    operations = [
        migrations.CreateModel(
            name='MutableModelParameters',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=256, unique=True)),
                ('value', models.CharField(max_length=256)),
                ('message', models.TextField(blank=True)),
            ],
            options={
                'verbose_name_plural': 'Parameters',
            },
        ),
        migrations.AddField(
            model_name='invite',
            name='first_name',
            field=models.CharField(blank=True, max_length=256),
        ),
        migrations.AddField(
            model_name='invite',
            name='last_name',
            field=models.CharField(blank=True, max_length=256),
        ),
        migrations.AddField(
            model_name='invite',
            name='pin_code',
            field=models.CharField(blank=True, db_index=True, max_length=10),
        ),
        migrations.AlterField(
            model_name='member',
            name='phone',
            field=models.CharField(max_length=40, unique=True),
        ),
        migrations.RemoveField(
            model_name='invite',
            name='token',
        ),
        migrations.AlterUniqueTogether(
            name='invite',
            unique_together=set([('phone', 'pin_code')]),
        ),
    ]
