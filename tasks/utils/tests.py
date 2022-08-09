from datetime import timedelta

from django.utils.http import urlsafe_base64_encode

import mock

from reporting.models import Event
from tasks.mixins.order_status import OrderStatus
from tasks.models import Customer, Order

CONFIRMED_BY_CUSTOMER = 'confirmed_by_customer'


def create_order_event_times(start_time, status_step=timedelta(minutes=5), to_status=OrderStatus.DELIVERED,
                             confirmed_by_customer=None):
    statuses = [OrderStatus.ASSIGNED, OrderStatus.IN_PROGRESS, OrderStatus.DELIVERED, CONFIRMED_BY_CUSTOMER]
    if (to_status != OrderStatus.DELIVERED) \
            or ((to_status == OrderStatus.DELIVERED) and (confirmed_by_customer is None)):
        confirmed_by_customer = False
    else:
        confirmed_by_customer = True
    time_for_status = [(start_time + status_step * i) for i in range(len(statuses) + int(confirmed_by_customer))]
    requested_statuses = statuses[:statuses.index(to_status) + 1]
    requested_dict = dict(zip(requested_statuses, time_for_status))
    return requested_dict


def create_order_for_test(test_class_item, manager, driver, order_data, switching_status_times):
    # Needed for creating all event-objects in tests

    from tasks.celery_tasks import generate_duration
    test_class_item.client.force_authenticate(manager)
    with mock.patch('django.utils.timezone.now') as post_now:
        post_now.return_value = switching_status_times[OrderStatus.ASSIGNED]
        test_class_item.client.post('/api/orders/', data=order_data)
    order = Order.objects.last()

    for order_status in switching_status_times.keys():
        if order_status != CONFIRMED_BY_CUSTOMER:
            test_class_item.client.force_authenticate(manager)
            with mock.patch('django.utils.timezone.now') as post_now:
                post_now.return_value = switching_status_times[order_status]
                test_class_item.client.patch('/api/orders/%s/' % order.order_id, {
                    'driver': driver.id,
                    'status': order_status,
                })
        else:
            test_class_item.client.logout()
            if CONFIRMED_BY_CUSTOMER in switching_status_times.keys():
                customer = Customer.objects.get(name=order_data['customer']['name'])
                with mock.patch('django.utils.timezone.now') as post_now:
                    post_now.return_value = switching_status_times[CONFIRMED_BY_CUSTOMER]
                    test_class_item.client.patch('/api/customers/%s/orders/%s/confirmation/' % (
                        urlsafe_base64_encode(str(customer.pk)), order.order_token
                    ), {'is_confirmed_by_customer': True, })

    generate_duration.delay(Event.objects.filter(orders__id=order.id).last().id)

    return order
