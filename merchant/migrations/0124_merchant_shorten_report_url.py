# Generated by Django 2.2.5 on 2020-03-16 09:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0123_merge_20200304_0125'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='shorten_report_url',
            field=models.BooleanField(default=False),
        ),
    ]