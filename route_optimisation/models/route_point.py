from datetime import timedelta

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from model_utils import Choices

from merchant.models import Hub
from route_optimisation.const import RoutePointKind
from tasks.models import Order
from tasks.models.functions import ConcatBarcodesInfo


class RoutePointQuerySet(models.QuerySet):
    def prefetch_for_content_type(self, content_type):
        qs = self.filter(point_content_type=content_type).order_by('number')
        if content_type.model == 'hub':
            qs = qs.prefetch_related('point_object__location')
        elif content_type.model == 'order':
            qs = qs.prefetch_related(
                'point_object__customer', 'point_object__deliver_address',
                'point_object__pickup', 'point_object__pickup_address',
                models.Prefetch('point_object__status_events', to_attr=Order.status_events.cache_name),
            )
        return qs

    HIDDEN = '_hidden'

    def _prepare_value_for_dataframe(self, value):
        if value is None:
            return ''
        return value

    def _prepare_for_dataframe(self, model, object_fields, qs=None):
        ct = ContentType.objects.get_for_model(model)
        point_id_to_object_id = {
            route_id: point_id
            for route_id, point_id, type_id in self.values_list('id', 'point_object_id', 'point_content_type_id')
            if type_id == ct.id
        }

        qs = qs if qs is not None else model.objects.all()
        object_qs = qs.filter(id__in=point_id_to_object_id.values())
        object_values = {item['id']: item for item in object_qs.values(*object_fields.keys())}
        object_ids = set(object_values.keys())

        """
        result = {
            <point id>: {<serializer field>: <value>},
        }
        """
        result = {
            point_id: {
                object_fields[key]: self._prepare_value_for_dataframe(value)
                for key, value in object_values[object_id].items()
                if object_fields[key] != RoutePointQuerySet.HIDDEN
            }
            for point_id, object_id in point_id_to_object_id.items()
            if object_id in object_ids
        }
        return result

    @staticmethod
    def order_fields():
        # '<queryset field>' : '<serializer field>'
        return {
            'id': RoutePointQuerySet.HIDDEN,
            'title': 'order_title',
            'order_id': 'order_id',
            'external_job__external_id': 'external_id',
            'pickup_address__address': 'pickup_address',
            'pickup_address__location': 'pickup_location',
            'deliver_address__address': 'address',
            'deliver_address__location': 'location',
            'pickup_after': 'pickup_after',
            'pickup_before': 'pickup_before',
            'deliver_after': 'deliver_after',
            'deliver_before': 'deliver_before',
            'pickup__name': 'pickup_name',
            'pickup__phone': 'pickup_phone',
            'customer__name': 'customer_name',
            'customer__phone': 'customer_phone',
            'concat_barcodes': 'barcodes',
            'capacity': 'capacity',
        }

    def order_fields_for_csv(self):
        qs = Order.aggregated_objects.all().annotate(concat_barcodes=ConcatBarcodesInfo(data_field='code_data'))
        return self._prepare_for_dataframe(Order, self.order_fields(), qs)

    @staticmethod
    def hub_fields():
        # '<queryset field>' : '<serializer field>'
        return {
            'id': 'hub_id',
            'name': 'hub_name',
            'location__address': 'address',
            'location__location': 'location',
        }

    def hub_fields_for_csv(self):
        return self._prepare_for_dataframe(Hub, self.hub_fields())


class RoutePointManager(models.Manager):
    _queryset_class = RoutePointQuerySet


class RoutePoint(models.Model):
    route = models.ForeignKey('route_optimisation.DriverRoute', related_name='points',
                              on_delete=models.CASCADE)
    number = models.PositiveIntegerField()

    POINT_KIND = Choices(
        (RoutePointKind.HUB, 'Hub'),
        (RoutePointKind.LOCATION, 'Location'),
        (RoutePointKind.PICKUP, 'Pickup'),
        (RoutePointKind.DELIVERY, 'Delivery'),
        (RoutePointKind.BREAK, 'Break'),
    )
    point_kind = models.CharField(max_length=12, choices=POINT_KIND)

    point_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True,
                                           related_name='route_points')
    point_object_id = models.PositiveIntegerField(null=True, blank=True)
    point_object = GenericForeignKey('point_content_type', 'point_object_id')

    next_point = models.ForeignKey(
        'route_optimisation.RoutePoint', related_name='past_point', on_delete=models.SET_NULL, null=True, blank=True,
        help_text='Reflects the actual next point the driver went to. '
                  'Some waypoints may be skipped by the driver as they were completed prematurely.',
    )

    service_time = models.PositiveIntegerField(blank=True, null=True)
    driving_time = models.PositiveIntegerField(blank=True, null=True)
    distance = models.PositiveIntegerField(blank=True, null=True)
    start_time = models.DateTimeField(blank=True, null=True)
    end_time = models.DateTimeField(blank=True, null=True)
    start_time_known_to_customer = models.DateTimeField(blank=True, null=True)
    path_polyline = models.TextField(blank=True, null=True)
    utilized_capacity = models.FloatField(blank=True, null=True)

    objects = RoutePointManager()

    @property
    def planned_order_arrival_interval(self):
        if self.start_time is not None:
            ROUND_DELTA = 15  # minutes
            dt = self.start_time
            dt -= timedelta(minutes=dt.minute % ROUND_DELTA, seconds=dt.second, microseconds=dt.microsecond)
            interval_start, interval_end = dt - timedelta(minutes=60), dt + timedelta(minutes=120)
        else:
            order = self.point_object
            interval_end = order.deliver_before
            interval_start = order.deliver_after \
                if order.deliver_after \
                else interval_end - timedelta(hours=order.merchant.delivery_interval)
        return interval_start, interval_end

    @property
    def point_location(self):
        if self.point_kind == RoutePointKind.HUB:
            return self.point_object.location
        elif self.point_kind == RoutePointKind.LOCATION:
            return self.point_object
        elif self.point_kind == RoutePointKind.PICKUP:
            return self.point_object.pickup_address
        elif self.point_kind == RoutePointKind.DELIVERY:
            return self.point_object.deliver_address
        elif self.point_kind == RoutePointKind.BREAK:
            return None

    @property
    def active(self):
        if self.point_kind in [RoutePointKind.HUB, RoutePointKind.LOCATION]:
            for point in self.route.points.all():
                if point.point_kind == RoutePointKind.DELIVERY:
                    if point.number < self.number and point.point_object.status not in [Order.DELIVERED, Order.FAILED]:
                        return True
                    if self.number < point.number and point.point_object.status in [Order.NOT_ASSIGNED, Order.ASSIGNED]:
                        return True
            return False
        elif self.point_kind == RoutePointKind.PICKUP:
            return self.point_object.status in [Order.ASSIGNED, Order.PICK_UP]
        elif self.point_kind == RoutePointKind.DELIVERY:
            return self.point_object.status in [Order.ASSIGNED, Order.PICK_UP, Order.PICKED_UP, Order.IN_PROGRESS]
        return False

    def __str__(self):
        return f'Route Point {self.POINT_KIND[self.point_kind]} ({self.id})'
