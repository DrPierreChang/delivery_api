# Generated by Django 2.2.5 on 2022-07-06 11:41

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('tasks', '0164_auto_20220527_2000'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='store_url',
            field=models.URLField(blank=True, null=True, verbose_name='Custom “URL” redirect link'),
        ),
    ]