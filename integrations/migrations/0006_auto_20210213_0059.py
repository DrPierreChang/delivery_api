# Generated by Django 2.2.5 on 2021-02-12 13:59

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0005_auto_20180717_0501_2'),
    ]

    operations = [
        migrations.AlterField(
            model_name='revelsystem',
            name='merchant',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='merchant.Merchant'),
        ),
    ]
