# Generated by Django 2.2.5 on 2020-09-09 14:46

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('route_optimisation', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='routeoptimisation',
            name='title',
        ),
    ]
