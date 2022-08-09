# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0103_merge_20180110_0211'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ErrorCode',
            new_name='TerminateCode'
        ),
        migrations.AddField(
            model_name='terminatecode',
            name='type',
            field=models.CharField(choices=[('error', 'Error'), ('success', 'Success')], default='error', max_length=7)
        ),
        migrations.AlterField(
            model_name='terminatecode',
            name='merchant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='terminate_codes', to='merchant.Merchant')
        ),
        migrations.RenameField(
            model_name='order',
            old_name='error_code',
            new_name='terminate_code'
        ),
        migrations.RenameField(
            model_name='order',
            old_name='error_comment',
            new_name='terminate_comment'
        )
    ]
