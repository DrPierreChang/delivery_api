# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2018-02-14 17:57
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('notification', '0020_auto_20180208_2201'),
    ]

    operations = [
        migrations.CreateModel(
            name='SMSMessage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sent_at', models.DateTimeField(null=True)),
                ('message', models.TextField()),
                ('phone', models.CharField(max_length=40)),
                ('sender', models.CharField(default='Radaro', max_length=40)),
                ('segment_count', models.PositiveSmallIntegerField()),
                ('response_data', models.TextField()),
                ('is_sent', models.BooleanField(default=False)),
                ('polymorphic_ctype', models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_notification.smsmessage_set+', to='contenttypes.ContentType')),
            ],
            options={
                'manager_inheritance_from_future': True,
            },
        ),
        migrations.RenameField(
            model_name='notification',
            old_name='kwargs',
            new_name='extra',
        ),
        migrations.AlterField(
            model_name='notification',
            name='sent_at',
            field=models.DateTimeField(null=True),
        ),
    ]
