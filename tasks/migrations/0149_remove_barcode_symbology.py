# Generated by Django 2.2.5 on 2020-07-23 11:29

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0148_auto_20200630_2017'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='barcode',
            name='symbology',
        ),
    ]
