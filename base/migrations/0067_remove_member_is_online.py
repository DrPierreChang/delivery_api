# Generated by Django 2.2.5 on 2020-03-03 12:41

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0066_auto_20200303_2341'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='member',
            name='is_online',
        ),
    ]
