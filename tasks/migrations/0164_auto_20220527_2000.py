# Generated by Django 2.2.5 on 2022-05-27 10:00

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('tasks', '0163_merge_20220420_2355'),
    ]

    operations = [
        migrations.AlterField(
            model_name='barcode',
            name='code_data',
            field=models.TextField(db_index=True),
        ),
    ]
