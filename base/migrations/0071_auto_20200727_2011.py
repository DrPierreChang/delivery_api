# Generated by Django 2.2.5 on 2020-07-27 10:11

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0070_auto_20200714_2110'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='car',
            name='description',
        ),
        migrations.RemoveField(
            model_name='car',
            name='hub',
        ),
        migrations.RemoveField(
            model_name='car',
            name='registration',
        ),
    ]