# Generated by Django 2.2.5 on 2020-03-18 07:34

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('webhooks', '0013_merchantwebhookevent'),
    ]

    operations = [
        migrations.AlterField(
            model_name='merchantapikeyevents',
            name='initiator',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
    ]
