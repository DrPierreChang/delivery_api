# Generated by Django 2.2.5 on 2020-06-29 10:58

from django.db import migrations


def fill_location_secondary_address(apps, schema_editor):
    Order = apps.get_model('tasks', 'Order')
    orders = Order.objects.exclude(deliver_address_2__exact='').select_related('deliver_address')
    for order in orders:
        location = order.deliver_address
        location.secondary_address = order.deliver_address_2
        location.save()


def fill_order_deliver_address_2(apps, schema_editor):
    Order = apps.get_model('tasks', 'Order')
    orders = Order.objects.exclude(deliver_address__secondary_address__exact='').select_related('deliver_address')
    for order in orders:
        order.deliver_address_2 = order.deliver_address.secondary_address
        order.save()


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0145_merge_20200622_1819'),
    ]

    operations = [
        migrations.RunPython(fill_location_secondary_address, reverse_code=fill_order_deliver_address_2),
        migrations.RemoveField(
            model_name='order',
            name='deliver_address_2',
        ),
    ]