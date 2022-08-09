# Generated by Django 2.2.5 on 2020-06-10 07:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0137_auto_20200306_2251'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderlocation',
            name='secondary_address',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterUniqueTogether(
            name='orderlocation',
            unique_together={('location', 'address', 'secondary_address', 'raw_address')},
        ),
    ]