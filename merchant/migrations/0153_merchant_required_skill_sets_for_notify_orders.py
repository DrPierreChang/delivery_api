# Generated by Django 2.2.5 on 2022-01-12 11:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('merchant', '0152_merge_20211205_0147'),
    ]

    operations = [
        migrations.AddField(
            model_name='merchant',
            name='required_skill_sets_for_notify_orders',
            field=models.ManyToManyField(blank=True, help_text='A notification will be sent if at least one of the skill sets specified here is on the order.', related_name='notifying_merchant', to='merchant.SkillSet', verbose_name='Required skill sets for notification of available not assigned orders'),
        ),
    ]