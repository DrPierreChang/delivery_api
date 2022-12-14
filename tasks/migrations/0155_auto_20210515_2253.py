# Generated by Django 2.2.5 on 2021-05-15 12:53

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0154_merge_20210205_2156'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConcatenatedOrder',
            fields=[
            ],
            options={
                'verbose_name': 'Concatenated order',
                'verbose_name_plural': 'Concatenated orders',
                'ordering': ('id',),
                'proxy': True,
                'default_related_name': 'concatenated_orders',
                'indexes': [],
                'constraints': [],
            },
            bases=('tasks.order',),
        ),
        migrations.AddField(
            model_name='order',
            name='deliver_day',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='is_concatenated_order',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='order',
            name='concatenated_order',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to='tasks.ConcatenatedOrder'),
        ),
    ]
