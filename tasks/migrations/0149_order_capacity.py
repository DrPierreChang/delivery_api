# Generated by Django 2.2.5 on 2020-07-14 14:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0148_auto_20200630_2017'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='capacity',
            field=models.PositiveIntegerField(help_text='Integer capacity value in local units of measurement', null=True),
        ),
    ]
