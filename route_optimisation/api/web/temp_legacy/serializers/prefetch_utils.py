from django.db.models import Prefetch, prefetch_related_objects

from merchant_extension.models import ResultChecklistConfirmationPhoto
from route_optimisation.models import DriverRoute
from tasks.models import ConcatenatedOrder, Order
from tasks.models.external import ExternalJob


def prefetch_for_route_optimisation(instances):
    orders, concatenated_orders = [], []
    for optimisation in instances:
        if 'routes' not in getattr(optimisation, '_prefetched_objects_cache', {}):
            qs = DriverRoute.objects.all().prefetch_generic_relations_for_web_api()
            prefetch_related_objects([optimisation], Prefetch('routes', queryset=qs))

        for route in optimisation.routes.all():
            route_orders = getattr(route, DriverRoute.get_prefetch_attr_name(Order))
            for order in route_orders:
                orders.append(order.point_object)
                if order.point_object.is_concatenated_order:
                    order.point_object._self_concatenated = ConcatenatedOrder.objects.get(id=order.point_object_id)
                    concatenated_orders.append(order.point_object._self_concatenated)
                    orders.append(order.point_object._self_concatenated)
                elif order.point_object.concatenated_order_id:
                    concatenated_orders.append(order.point_object.concatenated_order)
                    orders.append(order.point_object.concatenated_order)

    prefetch_list = (
        'starting_point', 'ending_point', 'manager',
        'pickup', 'pickup_address',
        'customer', 'deliver_address',
        'wayback_point', 'wayback_hub__location',
        'labels', 'barcodes', 'skill_sets', 'terminate_codes', 'skids',
        'pick_up_confirmation_photos', 'pre_confirmation_photos', 'order_confirmation_photos',
        'order_confirmation_documents', 'merchant',
        Prefetch('status_events', to_attr=Order.status_events.cache_name),
        Prefetch('order_route_point', to_attr=Order.order_route_point.cache_name),
        Prefetch('external_job', queryset=ExternalJob.objects.only('external_id')),
        Prefetch(
            'driver_checklist__confirmation_photos',
            queryset=ResultChecklistConfirmationPhoto.objects.only('id')
        ),
    )
    prefetch_related_objects(orders, *prefetch_list)
    only_for_concatenated_prefetch_list = (
        Prefetch('orders', queryset=Order.objects.all().prefetch_for_web_api().order_inside_concatenated()),
    )
    prefetch_related_objects(concatenated_orders, *only_for_concatenated_prefetch_list)
