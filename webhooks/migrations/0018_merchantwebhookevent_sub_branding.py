# Generated by Django 2.2.5 on 2021-04-02 16:49

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0142_subbranding_webhook_url'),
        ('webhooks', '0017_auto_20210215_2305'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchantwebhookevent',
            name='sub_branding',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='merchant.SubBranding'),
        ),
    ]
