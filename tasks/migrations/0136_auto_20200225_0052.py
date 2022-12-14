# Generated by Django 2.2.5 on 2020-02-24 13:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0135_order_deliver_address_2'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='deliver_after',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunSQL(
            "UPDATE tasks_order SET deliver_after=lower(delivery_interval) WHERE NOT isempty(delivery_interval);",
            reverse_sql="UPDATE tasks_order SET delivery_interval = tstzrange(deliver_after, deliver_before, '[)') "
                        "WHERE deliver_after IS NOT NULL"
        ),

        migrations.RemoveField(
            model_name='order',
            name='delivery_interval',
        )
    ]
