# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-09-13 12:47
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0089_merge_20180828_1933'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.RunSQL(
            "UPDATE merchant_merchant "
            "SET created_at = t.date_joined "
            "FROM "
            "(SELECT DISTINCT ON (merchant_id) merchant_id, date_joined "
            "FROM base_member ORDER BY merchant_id, date_joined) AS t "
            "WHERE t.merchant_id = merchant_merchant.id;", reverse_sql=migrations.RunSQL.noop
        )

    ]