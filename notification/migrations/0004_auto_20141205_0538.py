# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0003_auto_20141202_0711'),
    ]

    operations = [
        migrations.AlterField(
            model_name='device',
            name='real_type',
            field=models.ForeignKey(to='contenttypes.ContentType', on_delete=models.CASCADE),
        ),
    ]
