# Generated by Django 2.2.5 on 2022-06-08 08:39

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('route_optimisation', '0011_auto_20220520_1956'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='routeoptimisation',
            name='log',
        ),
    ]
