# -*- coding: utf-8 -*-
# Generated by Django 1.10.3 on 2016-12-07 10:36
from __future__ import unicode_literals

import json

from django.db import migrations


def values_migration(apps, schema_editor):
    MutableModelParameters = apps.get_model('base', 'MutableModelParameters')
    desc = {
        'min': 'The minimum value of this parameter is {}. ',
        'max': 'The maximum value of this parameter is {}. ',
        'choices': 'Possible choices are {}. '
    }
    with open('values.json', 'rt') as f:
        values = json.loads(f.read())
        for val in values:
            param = MutableModelParameters(type=val['type'], constraints=val['constraints'],
                                           description='', value=val['value'], name=val['name'],
                                           message=val['message'])
            param.description = 'Value {}. '.format(param.name)
            for k in param.constraints:
                param.description += desc[k].format(param.constraints[k])
            param.save()


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0040_auto_20161207_2046'),
    ]

    operations = [
        migrations.RunPython(code=values_migration, reverse_code=migrations.RunPython.noop)
    ]
