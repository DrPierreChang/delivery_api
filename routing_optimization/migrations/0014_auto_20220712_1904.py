# Generated by Django 2.2.5 on 2022-07-12 09:04

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('routing_optimization', '0013_routeoptimization_google_api_requests'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='routeoptimization',
            name='created_by',
        ),
        migrations.RemoveField(
            model_name='routeoptimization',
            name='merchant',
        ),
        migrations.RemoveField(
            model_name='routeoptimization',
            name='parent_optimization',
        ),
        migrations.RemoveField(
            model_name='routeoptimization',
            name='skipped_orders',
        ),
        migrations.RemoveField(
            model_name='routepoint',
            name='point_content_type',
        ),
        migrations.RemoveField(
            model_name='routepoint',
            name='route',
        ),
        migrations.DeleteModel(
            name='DriverRoute',
        ),
        migrations.DeleteModel(
            name='DriverRouteLocation',
        ),
        migrations.DeleteModel(
            name='RouteOptimization',
        ),
        migrations.DeleteModel(
            name='RoutePoint',
        ),
    ]
