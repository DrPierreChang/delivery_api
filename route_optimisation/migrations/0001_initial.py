# Generated by Django 2.2.5 on 2020-09-08 07:38

from django.conf import settings
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import django_fsm
import jsonfield.fields
import model_utils.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('merchant', '0133_merge_20200906_0033'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='DriverRoute',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('color', models.CharField(max_length=10)),
                ('options', django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True)),
                ('total_time', models.PositiveIntegerField(blank=True, null=True)),
                ('driving_time', models.PositiveIntegerField(blank=True, null=True)),
                ('driving_distance', models.PositiveIntegerField(blank=True, null=True)),
                ('real_time', models.PositiveIntegerField(blank=True, null=True)),
                ('real_distance', models.PositiveIntegerField(blank=True, null=True)),
                ('start_time', models.DateTimeField(blank=True, null=True)),
                ('end_time', models.DateTimeField(blank=True, null=True)),
                ('driver', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='routes', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='RoutePoint',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.PositiveIntegerField()),
                ('point_object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('service_time', models.PositiveIntegerField(blank=True, null=True)),
                ('driving_time', models.PositiveIntegerField(blank=True, null=True)),
                ('distance', models.PositiveIntegerField(blank=True, null=True)),
                ('start_time', models.DateTimeField(blank=True, null=True)),
                ('end_time', models.DateTimeField(blank=True, null=True)),
                ('path_polyline', models.TextField(blank=True, null=True)),
                ('utilized_capacity', models.PositiveIntegerField(blank=True, null=True)),
                ('point_content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='route_points', to='contenttypes.ContentType')),
                ('route', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='points', to='route_optimisation.DriverRoute')),
            ],
        ),
        migrations.CreateModel(
            name='RouteOptimisation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=50)),
                ('type', models.CharField(choices=[('SOLO', 'Solo'), ('FAST', 'Fast'), ('ADVANCED', 'Advanced'), ('SCHEDULED', 'Scheduled'), ('PTV_EXPORT', 'PTV Export')], max_length=10)),
                ('day', models.DateField()),
                ('options', django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict)),
                ('optimisation_options', django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict)),
                ('google_api_requests', django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True)),
                ('log', django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict)),
                ('state', models.CharField(choices=[('CREATED', 'Created'), ('VALIDATION', 'Validation'), ('OPTIMISING', 'Optimising'), ('COMPLETED', 'Optimisation completed'), ('RUNNING', 'Running'), ('FINISHED', 'Finished'), ('FAILED', 'Failed'), ('REMOVED', 'Removed')], default='CREATED', max_length=12)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_optimisations', to=settings.AUTH_USER_MODEL)),
                ('merchant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='optimisations', to='merchant.Merchant')),
            ],
        ),
        migrations.CreateModel(
            name='OptimisationTask',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('status', django_fsm.FSMField(default='created', max_length=50)),
                ('log', jsonfield.fields.JSONField(default=[])),
                ('optimisation', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='delayed_task', to='route_optimisation.RouteOptimisation')),
            ],
            options={
                'ordering': ('-id',),
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='driverroute',
            name='optimisation',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='routes', to='route_optimisation.RouteOptimisation'),
        ),
        migrations.AlterUniqueTogether(
            name='driverroute',
            unique_together={('optimisation', 'color')},
        ),
    ]
