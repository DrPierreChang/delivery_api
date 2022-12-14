# Generated by Django 2.2.5 on 2020-11-24 14:17

from django.db import migrations, models
import location_field.models.plain


class Migration(migrations.Migration):

    dependencies = [
        ('route_optimisation', '0005_auto_20201017_0156'),
    ]

    operations = [
        migrations.CreateModel(
            name='DriverRouteLocation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('address', models.CharField(blank=True, max_length=255)),
                ('location', location_field.models.plain.PlainLocationField(default=None, max_length=63)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('description', models.CharField(blank=True, max_length=150)),
            ],
            options={
                'ordering': ('created_at',),
            },
        ),
    ]
