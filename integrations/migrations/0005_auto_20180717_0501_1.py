# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-07-16 19:01
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('integrations', '0004_revelsystem_importing'),
    ]

    operations = [
        migrations.RenameField(
            model_name='revelsystem',
            old_name='last_update',
            new_name='modified',
        ),
        migrations.AddField(
            model_name='revelsystem',
            name='created',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='revelsystem',
            name='creator',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='revelsystem',
            name='merchant',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='merchant.Merchant'),
        ),
        migrations.AlterField(
            model_name='revelsystem',
            name='created',
            field=model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False,
                                                      verbose_name='created'),
        ),
        migrations.AlterField(
            model_name='revelsystem',
            name='modified',
            field=model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False,
                                                           verbose_name='modified'),
        ),
    ]