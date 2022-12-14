# -*- coding: utf-8 -*-
# Generated by Django 1.9.11 on 2017-04-05 14:34
from __future__ import unicode_literals

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion

import radaro_utils.files.utils
import radaro_utils.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Answer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('choice', models.NullBooleanField()),
                ('created_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='Checklist',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Question',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField()),
                ('description', models.TextField(blank=True, null=True)),
                ('correct_answer', models.BooleanField(default=True)),
                ('description_image', models.ImageField(blank=True, null=True, upload_to=radaro_utils.files.utils.get_upload_path)),
                ('consecutive_number', models.IntegerField(null=True, validators=[django.core.validators.MinValueValidator(1)])),
                ('checklist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='questions', to='merchant_extension.Checklist')),
            ],
            options={
                'ordering': ('checklist', 'consecutive_number'),
            },
            bases=(radaro_utils.models.ResizeImageMixin, models.Model),
        ),
        migrations.CreateModel(
            name='ResultChecklist',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_of_risk_assessment', models.DateTimeField(auto_now=True, null=True)),
                ('confirmation_signature', models.ImageField(blank=True, null=True, upload_to=radaro_utils.files.utils.get_upload_path)),
                ('confirmation_comment', models.TextField(blank=True, null=True)),
                ('is_correct', models.NullBooleanField()),
                ('checklist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='merchant_extension.Checklist')),
            ],
        ),
        migrations.CreateModel(
            name='ResultChecklistConfirmationPhoto',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to=radaro_utils.files.utils.get_upload_path)),
                ('result_checklist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='confirmation_photos', to='merchant_extension.ResultChecklist')),
            ],
            bases=(radaro_utils.models.ResizeImageMixin, models.Model),
        ),
        migrations.AddField(
            model_name='answer',
            name='question',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='merchant_extension.Question'),
        ),
        migrations.AddField(
            model_name='answer',
            name='result_checklist',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='merchant_extension.ResultChecklist'),
        ),
        migrations.AlterUniqueTogether(
            name='question',
            unique_together=set([('consecutive_number', 'checklist')]),
        ),
        migrations.AlterUniqueTogether(
            name='answer',
            unique_together=set([('question', 'result_checklist')]),
        ),
    ]
