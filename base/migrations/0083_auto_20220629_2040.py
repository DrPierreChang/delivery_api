# Generated by Django 2.2.5 on 2022-06-29 10:40

from django.db import migrations, models
import base.models.members


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0082_auto_20220322_2043'),
    ]

    operations = [
        migrations.AddField(
            model_name='member',
            name='deleted',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='member',
            name='deleted_at',
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
        migrations.AlterModelManagers(
            name='member',
            managers=[
                ('objects', base.models.members.MembersManager()),
                ('drivers', base.models.members.ActiveDriversManager()),
                ('drivers_with_statuses', base.models.members.ActiveDriversManagerWithStatuses()),
                ('all_drivers', base.models.members.DriversManager()),
                ('managers', base.models.members.ManagersManager()),
                ('all_objects', models.Manager()),
            ],
        ),
    ]