# Generated by Django 2.2.5 on 2020-07-14 11:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0130_merge_20200622_2348'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='enable_job_capacity',
            field=models.BooleanField(default=False),
        ),
    ]
