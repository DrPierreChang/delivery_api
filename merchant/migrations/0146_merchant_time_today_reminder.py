# Generated by Django 2.2.5 on 2021-07-29 12:29

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0145_merge_20210713_2300'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='time_today_reminder',
            field=models.TimeField(default=datetime.time, verbose_name='Today delivery reminder', help_text='Time at which today upcoming delivery notification is sent according to the merchant timezone.',),
        ),
    ]