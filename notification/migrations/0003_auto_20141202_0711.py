# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0002_notification'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='notification',
            name='device',
        ),
        migrations.AddField(
            model_name='notification',
            name='devices',
            field=models.ManyToManyField(related_name='sent_notifications', to='notification.Device'),
            preserve_default=True,
        ),
    ]
