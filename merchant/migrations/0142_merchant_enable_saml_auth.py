# Generated by Django 2.2.5 on 2021-04-09 11:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0141_merge_20210315_2051'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='enable_saml_auth',
            field=models.BooleanField(default=False, verbose_name='Enable SAML auth'),
        ),
    ]
