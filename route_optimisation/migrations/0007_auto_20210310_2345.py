# Generated by Django 2.2.5 on 2021-03-10 12:45

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('route_optimisation', '0006_driverroutelocation'),
    ]

    operations = [
        migrations.AddField(
            model_name='routeoptimisation',
            name='external_source_id',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='routeoptimisation',
            name='external_source_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='contenttypes.ContentType'),
        ),
    ]
