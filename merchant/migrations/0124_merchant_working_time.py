# Generated by Django 2.2.5 on 2020-04-09 13:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0123_merge_20200304_0125'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='working_time',
            field=models.IntegerField(blank=True, default=8, help_text='"Working" time after which the driver will be moved to the "not working" status', null=True),
        ),
    ]
