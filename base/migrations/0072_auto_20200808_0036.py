# Generated by Django 2.2.5 on 2020-08-07 14:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0071_auto_20200727_2011'),
    ]

    operations = [
        migrations.AlterField(
            model_name='car',
            name='capacity',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
