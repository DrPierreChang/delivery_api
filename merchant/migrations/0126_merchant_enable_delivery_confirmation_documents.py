# Generated by Django 2.2.5 on 2020-05-18 10:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0125_merge_20200506_2307'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='enable_delivery_confirmation_documents',
            field=models.BooleanField(default=False, help_text='To activate this option, require an enable delivery confirmation'),
        ),
    ]
