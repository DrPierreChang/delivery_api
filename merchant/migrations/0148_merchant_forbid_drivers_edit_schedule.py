# Generated by Django 2.2.5 on 2021-09-16 06:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0147_merge_20210813_2132'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='forbid_drivers_edit_schedule',
            field=models.BooleanField(default=False, verbose_name='Restrict drivers from editing schedules'),
        ),
    ]