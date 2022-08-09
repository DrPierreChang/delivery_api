# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-05-10 16:53
from __future__ import unicode_literals

import json
import re

from dateutil import parser
from django.db import migrations
import jsonfield.fields

from radaro_utils.serializers.fields import UTCTimestampField

log_list = ()
serializer = UTCTimestampField(precision=UTCTimestampField.MS)


class Migration(migrations.Migration):
    def forward_pack(apps, schema_migration):
        ExportReportInstance = apps.get_model('reporting', 'exportreportinstance')
        log_list = tuple(ExportReportInstance.objects.all().values('comment', 'id'))
        with open('reports.json', 'wt') as f:
            f.write(json.dumps(log_list))

    def forward_unpack(apps, schema_migration):
        ExportReportInstance = apps.get_model('reporting', 'exportreportinstance')
        for log in log_list:
            match_dict = [
                re.match(r'\[(?P<level>[A-Z]+): (?P<happened_at>[0-9\-:.\s]+)\] (?P<message>[\w\s\.\,\!\?]+)',
                         line).groupdict()
                for line in log['comment'].split('\n')
            ]
            log_obj = ExportReportInstance.objects.get(id=log['id'])
            log_obj.log_event = [{
                'happened_at': serializer.to_representation(parser.parse(log_line['happened_at'] + '+00:00')),
                'level': log_line['level'],
                'message': log_line['message']
            } for log_line in match_dict]
            log_obj.save()

    dependencies = [
        ('reporting', '0010_auto_20170104_2248'),
    ]

    operations = [
        migrations.RunPython(forward_pack, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='exportreportinstance',
            name='comment',
        ),
        migrations.AddField(
            model_name='exportreportinstance',
            name='log',
            field=jsonfield.fields.JSONField(default=[]),
        ),
        migrations.RunPython(forward_unpack, reverse_code=migrations.RunPython.noop),
    ]