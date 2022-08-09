# Generated by Django 2.2.5 on 2021-04-01 10:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0141_merge_20210315_2051'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='pickup_service_time',
            field=models.PositiveSmallIntegerField(choices=[(3, '3 Minutes'), (5, '5 Minutes'), (10, '10 Minutes'), (15, '15 Minutes'), (20, '20 Minutes'), (30, '30 Minutes'), (45, '45 Minutes'), (60, '1 Hour'), (90, '90 Minutes'), (120, '2 Hours')], default=5, help_text='Set average duration of time a driver needs to spend to on pickup site. This setting is useful only with "route optimisation" enabled.'),
        ),
    ]
