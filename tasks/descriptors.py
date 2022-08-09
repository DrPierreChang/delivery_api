from collections import Iterable

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from radaro_utils.descriptors import ModelFieldDescriptor
from reporting.models import Event
from route_optimisation.const import RoutePointKind
from tasks.mixins.order_status import OrderStatus


class OrderStatusEventGetter(object):
    def __init__(self, events):
        self.events = events

    def __getitem__(self, order_statuses):
        order_statuses = order_statuses \
            if (isinstance(order_statuses, Iterable) and not isinstance(order_statuses, str)) \
            else [order_statuses]
        for ev in self.events:
            if ev.event == Event.CHANGED and ev.new_value in order_statuses:
                return ev

    def get_assign_event(self):
        # In case Order was created with 'assigned' status, there might be no status-event.
        # So we need to find creation event
        status_event = self[OrderStatus.ASSIGNED]
        if status_event:
            return status_event
        creation_event = self._get_creation_event()
        if creation_event and creation_event.obj_dump.get('status') == OrderStatus.ASSIGNED:
            return creation_event

    def _get_creation_event(self):
        for ev in self.events:
            if ev.event == Event.CREATED:
                return ev


class OrderStatusesEventsDescriptor(ModelFieldDescriptor):
    """
    Descriptor to fetch status events for order.
    """

    cache_name = '_status_events'
    single = False
    only_fields = ('id', 'happened_at', 'object_id', 'new_value', 'obj_dump', 'event')

    def __init__(self):
        super().__init__()
        status_change_statement = Q(field='status', new_value__in=OrderStatus.status_groups.ALL, event=Event.CHANGED)
        create_event_statement = Q(event=Event.CREATED)
        self.search_statement = status_change_statement | create_event_statement

    def get_foreign_related_value(self, instance):
        return instance.object_id

    def get_local_related_value(self, instance):
        return instance.id

    def get_default_queryset(self):
        return Event.objects.all().only(*self.only_fields)

    def filter_queryset(self, instances, queryset):
        from tasks.models import ConcatenatedOrder, Order
        ct = ContentType.objects.get_for_model(Order, for_concrete_model=False)
        cct = ContentType.objects.get_for_model(ConcatenatedOrder, for_concrete_model=False)
        type_and_id_filtering = Q(object_id__in=[instance.id for instance in instances], content_type__in=[ct, cct])
        qs = queryset.filter(self.search_statement).filter(type_and_id_filtering)
        return qs

    def get_value_by_python(self, instance):
        return instance.events.filter(self.search_statement).only(*self.only_fields)

    def __get__(self, instance, instance_type=None):
        ret = super(OrderStatusesEventsDescriptor, self).__get__(instance, instance_type)
        if ret is self:
            return ret
        return OrderStatusEventGetter(ret)


class OrderInQueueDescriptor(ModelFieldDescriptor):
    cache_name = '_in_queue'
    single = False
    monitored_statuses = [OrderStatus.ASSIGNED, OrderStatus.PICK_UP, OrderStatus.PICKED_UP, OrderStatus.IN_PROGRESS]

    def get_foreign_related_value(self, instance):
        return instance.driver_id

    def get_local_related_value(self, instance):
        return instance.driver_id

    def get_default_queryset(self):
        from tasks.models import Order
        orders = Order.aggregated_objects.filter(status__in=OrderStatus.status_groups.ACTIVE_DRIVER)
        return orders.order_active_orders_for_driver().only('id', 'driver_id', 'bulk')

    def filter_queryset(self, instances, queryset):
        driver_ids = {order.driver_id for order in instances if order.status in self.monitored_statuses}
        return queryset.filter(driver_id__in=list(driver_ids)).exclude_concatenated_child()

    def get_value_by_python(self, instance):
        if instance.status not in self.monitored_statuses:
            return []
        qs = self.get_default_queryset().filter(driver_id=instance.driver_id).exclude_concatenated_child()
        return list(qs)

    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self
        orders = super().__get__(instance, instance_type)
        return self._find_num_in_queue(instance, orders)

    @staticmethod
    def _find_num_in_queue(instance, orders):
        id = instance.concatenated_order_id or instance.id
        for num, order in enumerate(orders):
            if order.id == id:
                return num + 1


class OrderInDriverRouteQueueDescriptor(ModelFieldDescriptor):
    # The descriptor receives all orders in the queue and returns the order position in the queue
    
    cache_name = '_in_driver_route_queue'
    single = False
    monitored_statuses = [OrderStatus.ASSIGNED, OrderStatus.PICK_UP, OrderStatus.PICKED_UP, OrderStatus.IN_PROGRESS]

    def get_foreign_related_value(self, instance):
        return instance.route_id

    def get_local_related_value(self, instance):
        # Corresponds to the expression instance.route_points.last().route_id
        return instance.cached_route_id

    def get_default_queryset(self):
        from route_optimisation.models import RouteOptimisation, RoutePoint
        from tasks.models import Order

        ct = ContentType.objects.get_for_model(Order)
        order_points = RoutePoint.objects.filter(
            point_content_type=ct,
            point_kind=RoutePointKind.DELIVERY,
            route__optimisation__state__in=(RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING),
        )
        return order_points.order_by('number')

    def filter_queryset(self, instances, queryset):
        # Returns points only from those routes that contain processed orders

        order_ids = {
            order.concatenated_order_id or order.id
            for order in instances
            if order.status in self.monitored_statuses
        }
        order_points = queryset.filter(point_object_id__in=order_ids)
        # Dictionary is created on the principle - order id : last route id
        order_route_ids = dict(order_points.values_list('point_object_id', 'route_id').order_by('route_id'))

        for order in instances:
            order.cached_route_id = order_route_ids.get(order.concatenated_order_id or order.id, None)

        return queryset.filter(route_id__in=order_route_ids.values()).prefetch_related('point_object')

    def get_value_by_python(self, instance):
        if instance.concatenated_order is not None:
            instance = instance.concatenated_order

        if instance.status not in self.monitored_statuses:
            return []
        route_point_getter = instance.order_route_point
        if not route_point_getter:
            return []
        route_point = route_point_getter.get_by_kind(RoutePointKind.DELIVERY)
        if not route_point:
            return []

        qs = self.get_default_queryset().filter(route_id=route_point.route_id)
        return list(qs)

    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self
        order_points = super().__get__(instance, instance_type)
        order_points = [
            p for p in order_points if p.point_object.status in OrderInDriverRouteQueueDescriptor.monitored_statuses
        ]
        return {
            'number': self._find_num_in_queue(instance, order_points),
            'all': len(order_points)
        }

    @staticmethod
    def _find_num_in_queue(order, order_points):
        order_id = order.concatenated_order_id or order.id
        for num, order_point in enumerate(order_points):
            if order_point.point_object_id == order_id:
                return num + 1


class OrderRoutePointGetter(object):
    def __init__(self, points):
        self.points = points

    def get_by_kind(self, point_kind):
        for point in self.points:
            if point.point_kind == point_kind:
                return point


class OrderRoutePointDescriptor(ModelFieldDescriptor):
    # The descriptor return active order's optimisation point

    cache_name = '_order_route_point'
    single = False

    def get_foreign_related_value(self, instance):
        return instance.point_object_id

    def get_local_related_value(self, instance):
        return instance.id

    def get_default_queryset(self):
        from route_optimisation.models import RouteOptimisation, RoutePoint
        from tasks.models import Order

        ct = ContentType.objects.get_for_model(Order)
        order_points = RoutePoint.objects.filter(
            point_content_type=ct,
            route__optimisation__state__in=(RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING),
        ).prefetch_related('point_object')
        return order_points

    def filter_queryset(self, instances, queryset):
        order_ids = {order.id for order in instances}
        return queryset.filter(point_object_id__in=order_ids)

    def get_value_by_python(self, instance):
        qs = self.get_default_queryset().filter(point_object_id=instance.id)
        return list(qs)

    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self
        points = super().__get__(instance, instance_type)
        if not points:
            return
        return OrderRoutePointGetter(points)
