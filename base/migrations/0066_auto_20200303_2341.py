# Generated by Django 2.2.5 on 2020-03-03 12:41

from django.db import migrations, models


def is_online_to_work_status(apps, schema_editor):
    Member = apps.get_model('base', 'Member')
    Member.objects.filter(is_online=True).update(work_status='working')
    Member.objects.filter(is_online=False).update(work_status='not_working')


def work_status_to_is_online(apps, schema_editor):
    Member = apps.get_model('base', 'Member')
    Member.objects.filter(work_status='not_working').update(is_online=False)
    Member.objects.exclude(work_status='not_working').update(is_online=True)


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0065_auto_20200130_0034'),
    ]

    operations = [
        migrations.AddField(
            model_name='member',
            name='work_status',
            field=models.CharField(
                choices=[('working', 'Working'), ('not_working', 'Not working'), ('on_break', 'On break')],
                default='not_working', max_length=15),
        ),
        migrations.RunPython(is_online_to_work_status, work_status_to_is_online),
    ]
