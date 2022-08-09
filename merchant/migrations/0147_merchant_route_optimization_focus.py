# Generated by Django 2.2.5 on 2021-09-01 08:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0146_merchant_time_today_reminder'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='route_optimization_focus',
            field=models.CharField(choices=[('minimal_time', 'Minimal route time (drivers might be skipped)'), ('time_balance', 'Balanced by route time (route assignment among all drivers)'), ('all', 'Combined optimisation (based on minimal & balanced by route time)'), ('old', 'Old algorithm version')], default='old', help_text='Set, what to focus on for group optimisation. This setting is useful only with "route optimisation" enabled.', max_length=50, verbose_name='route optimisation focus'),
        ),
    ]