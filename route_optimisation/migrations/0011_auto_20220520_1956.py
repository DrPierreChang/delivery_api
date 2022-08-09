import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


def fill_ro_log_model(apps, schema):
    RouteOptimisation = apps.get_model('route_optimisation', 'RouteOptimisation')
    ROLog = apps.get_model('route_optimisation', 'ROLog')
    batch_size, step = 100, 1000
    top_id = step
    while RouteOptimisation.objects.all().filter(optimisation_log_id__isnull=True).exists():
        c = RouteOptimisation.objects.all().filter(optimisation_log_id__isnull=True).count()
        print(f'updating to {top_id} id, left {c} optimisations')
        optimisations = RouteOptimisation.objects.all().filter(optimisation_log_id__isnull=True, id__lte=top_id)
        for_save = []
        for ro in optimisations:
            ro.optimisation_log = ROLog(log=ro.log)
            for_save.append(ro.optimisation_log)
        ROLog.objects.bulk_create(for_save, batch_size=batch_size)
        for_update = []
        for ro in optimisations:
            ro.optimisation_log = ro.optimisation_log
            assert ro.optimisation_log is not None and ro.optimisation_log.id == ro.optimisation_log_id
            for_update.append(ro)
        RouteOptimisation.objects.bulk_update(for_update, ('optimisation_log',), batch_size=batch_size)
        top_id += step
    c = RouteOptimisation.objects.all().filter(optimisation_log_id__isnull=True).count()
    print(f'updated, left {c} optimisations')


def fill_log_field(apps, schema):
    RouteOptimisation = apps.get_model('route_optimisation', 'RouteOptimisation')
    batch_size, step = 100, 1000
    top_id = step
    while RouteOptimisation.objects.all().filter(optimisation_log_id__isnull=False).exists():
        c = RouteOptimisation.objects.all().filter(optimisation_log_id__isnull=False).count()
        print(f'updating to {top_id} id, left {c} optimisations')
        optimisations = RouteOptimisation.objects.all().filter(optimisation_log_id__isnull=False, id__lte=top_id)\
            .select_related('optimisation_log')
        for_update = []
        for ro in optimisations:
            ro.log = ro.optimisation_log.log
            ro.optimisation_log = None
            for_update.append(ro)
        RouteOptimisation.objects.bulk_update(for_update, ('optimisation_log', 'log'), batch_size=batch_size)
        top_id += step
    c = RouteOptimisation.objects.all().filter(optimisation_log_id__isnull=False).count()
    print(f'updating, left {c} optimisations')


class Migration(migrations.Migration):

    dependencies = [
        ('route_optimisation', '0010_auto_20220214_2031'),
    ]

    operations = [
        migrations.CreateModel(
            name='ROLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('log', django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict)),
            ],
        ),
        migrations.AddField(
            model_name='routeoptimisation',
            name='optimisation_log',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    to='route_optimisation.ROLog'),
        ),
        migrations.RunPython(fill_ro_log_model, reverse_code=fill_log_field),
        migrations.AlterField(
            model_name='routeoptimisation',
            name='log',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=None, null=True),
        ),
    ]
