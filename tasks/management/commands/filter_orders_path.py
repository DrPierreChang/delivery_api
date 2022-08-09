from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db.models import Q

from driver.models import DriverLocation
from reporting.models import Event
from routing.utils import filter_driver_path
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order


class Command(BaseCommand):
    help = 'Filter path for finished jobs.'

    def add_arguments(self, parser):
        parser.add_argument('order_id', nargs='*', type=int, help='order ids for filtering')

    @staticmethod
    def update_driver_path(order_id):
        order = Order.objects.filter(id=order_id).first()
        has_pick_up = order.events.all().filter(field='status', new_value=OrderStatus.PICK_UP).exists()
        start_status = OrderStatus.PICK_UP if has_pick_up else OrderStatus.IN_PROGRESS
        order_ct = ContentType.objects.get_for_model(Order)
        start = Event.objects.filter(object_id=order.id, content_type=order_ct, new_value=start_status) \
            .values_list('happened_at', flat=True).last()
        finish = Event.objects.filter(
            object_id=order.id,
            content_type=order_ct,
            new_value__in=[OrderStatus.DELIVERED, OrderStatus.FAILED],
        ).values_list('happened_at', flat=True).last()
        if not (start and finish) or finish < start:
            return 0
        driver_locations = DriverLocation.objects.filter(member=order.driver, accuracy__lte=settings.MAX_ACCURACY_RANGE) \
            .filter(Q(created_at__gte=start) & Q(created_at__lte=finish))
        if driver_locations:
            path, path_length = filter_driver_path(list(driver_locations))
            duration = finish - start
            params = {'path': path, 'duration': duration, 'order_distance': path_length}
            return Order.objects.filter(id=order_id).update(**params)
        return 0

    def handle(self, *args, **options):
        order_ids = options.get('order_id')
        orders = Order.objects.filter(status__in=OrderStatus.status_groups.FINISHED)
        updated = 0
        if order_ids:
            orders = Order.objects.filter(order_id__in=order_ids)
        for order in orders:
            updated += Command.update_driver_path(order.id)
        self.stdout.write(msg='{} orders successfully updated'.format(updated), style_func=self.style.SUCCESS)
