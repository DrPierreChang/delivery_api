# Generated by Django 2.2.5 on 2020-06-16 12:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0128_merge_20200608_2133'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='enable_reminder_to_attach_confirmation_documents',
            field=models.BooleanField(default=False),
        ),
    ]
