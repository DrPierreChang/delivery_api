# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AvailabilityTest',
            fields=[
                ('primary_key', models.CharField(max_length=20, serialize=False, primary_key=True)),
                ('last_access', models.DateTimeField(help_text='Datetime of last access to this model from the celery task')),
            ],
        ),
    ]
