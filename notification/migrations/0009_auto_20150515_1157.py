# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0008_auto_20150225_0833'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='created_at',
            field=models.DateTimeField(default=datetime.datetime(2015, 5, 15, 11, 57, 34, 667170, tzinfo=utc), auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='device',
            name='updated_at',
            field=models.DateTimeField(default=datetime.datetime(2015, 5, 15, 11, 57, 38, 315029, tzinfo=utc), verbose_name='Last activity at', auto_now=True),
            preserve_default=False,
        ),
    ]
