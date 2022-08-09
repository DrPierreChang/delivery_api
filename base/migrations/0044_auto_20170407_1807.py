# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2017-04-07 08:07
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    def create_parameter(apps, schema_editor):
        MutableModelParameters = apps.get_model('base', 'MutableModelParameters')
        path_param = MutableModelParameters.objects.create(name='PATH_IMPROVING',
                                                           type='bool',
                                                           message='This parameter enables or disables advanced path '
                                                                   'processing.')
        path_param.val = False
        path_param.save()

    dependencies = [
        ('base', '0043_auto_20170117_1929'),
    ]

    operations = [
        migrations.RunPython(code=create_parameter, reverse_code=migrations.RunPython.noop)
    ]