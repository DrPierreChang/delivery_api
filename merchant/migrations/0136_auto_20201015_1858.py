# Generated by Django 2.2.5 on 2020-10-15 07:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0135_merge_20201014_2150'),
    ]

    operations = [
        migrations.AlterField(
            model_name='merchantgroup',
            name='webhook_url',
            field=models.CharField(blank=True, max_length=500),
        ),
    ]