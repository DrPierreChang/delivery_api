# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import push_notifications.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('contenttypes', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255, null=True, verbose_name='Name', blank=True)),
                ('active', models.BooleanField(default=True, help_text='Inactive devices will not be sent notifications', verbose_name='Is active')),
                ('date_created', models.DateTimeField(auto_now_add=True, verbose_name='Creation date', null=True)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='APNSDevice',
            fields=[
                ('device_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='notification.Device', on_delete=models.CASCADE)),
                ('device_id', models.UUIDField(help_text='UDID / UIDevice.identifierForVendor()', max_length=32, null=True, verbose_name='Device ID', blank=True)),
                ('registration_id', models.CharField(unique=True, max_length=64, verbose_name='Registration ID')),
            ],
            options={
                'verbose_name': 'APNS device',
            },
            bases=('notification.device',),
        ),
        migrations.CreateModel(
            name='GCMDevice',
            fields=[
                ('device_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='notification.Device', on_delete=models.CASCADE)),
                ('device_id', push_notifications.fields.HexIntegerField(help_text='ANDROID_ID / TelephonyManager.getDeviceId() (always as hex)', null=True, verbose_name='Device ID', blank=True)),
                ('registration_id', models.TextField(verbose_name='Registration ID')),
            ],
            options={
                'verbose_name': 'GCM device',
            },
            bases=('notification.device',),
        ),
        migrations.AddField(
            model_name='device',
            name='real_type',
            field=models.ForeignKey(editable=False, to='contenttypes.ContentType', on_delete=models.CASCADE),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='device',
            name='user',
            field=models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE),
            preserve_default=True,
        ),
    ]
