# Generated by Django 2.2.5 on 2020-10-15 07:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webhooks', '0015_auto_20200731_1753'),
    ]

    operations = [
        migrations.AlterField(
            model_name='merchantwebhookevent',
            name='webhook_url',
            field=models.CharField(max_length=500),
        ),
    ]