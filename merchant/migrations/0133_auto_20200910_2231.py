# Generated by Django 2.2.5 on 2020-09-10 12:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0132_merchant_enable_skids'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='default_skid_height',
            field=models.FloatField(default=40, verbose_name='default SKID height'),
        ),
        migrations.AddField(
            model_name='merchant',
            name='default_skid_length',
            field=models.FloatField(default=48, verbose_name='default SKID length'),
        ),
        migrations.AddField(
            model_name='merchant',
            name='default_skid_width',
            field=models.FloatField(default=48, verbose_name='default SKID width'),
        ),
    ]
