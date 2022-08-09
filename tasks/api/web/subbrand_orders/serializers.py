from django.contrib.auth import get_user_model

from rest_framework import serializers

from merchant.api.web.labels.serializers import LabelSerializer
from route_optimisation.const import RoutePointKind
from tasks.api.legacy.serializers import PublicReportSerializer
from tasks.api.legacy.serializers.core import OrderLocationSerializerV2
from tasks.api.legacy.serializers.customers import CustomerSerializer
from tasks.models import Order
from tasks.utils.order_eta import ETAToOrders


class ShortDriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ('id', 'email', 'full_name', 'status')


class ListSubManagerOrderListSerializer(serializers.ListSerializer):
    eta_dict = {}

    @property
    def data(self):
        self.eta_dict = ETAToOrders().get_eta_many_orders(self.instance, self.context['request'].user.current_merchant)
        return super(ListSubManagerOrderListSerializer, self).data


class ListSubManagerOrderSerializer(serializers.ModelSerializer):
    server_entity_id = serializers.IntegerField(source='id')
    driver = ShortDriverSerializer()
    customer = CustomerSerializer()
    deliver_address = OrderLocationSerializerV2()
    deliver_address_2 = serializers.CharField(source='deliver_address.secondary_address', read_only=True)
    pickup_address = OrderLocationSerializerV2()
    external_id = serializers.SerializerMethodField()
    eta = serializers.SerializerMethodField()
    labels = LabelSerializer(many=True)
    delivery_interval = serializers.SerializerMethodField()
    planned_arrival = serializers.SerializerMethodField()
    planned_arrival_interval = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ('server_entity_id', 'customer', 'driver', 'deliver_address', 'deliver_address_2', 'pickup_address',
                  'external_id', 'order_id', 'title', 'in_queue', 'eta', 'deliver_after', 'deliver_before',
                  'delivery_interval', 'status', 'labels', 'finished_at', 'planned_arrival',
                  'planned_arrival_interval',)
        read_only_fields = ('external_id',)
        list_serializer_class = ListSubManagerOrderListSerializer

    def get_external_id(self, order):
        return order.external_job.external_id if order.external_job else None

    def get_eta(self, order):
        return self.parent.eta_dict[order.concatenated_order_id or order.id]['value']

    def get_delivery_interval(self, order):
        return {'upper': order.deliver_before, 'lower': order.deliver_after}

    def _get_delivery_route_point(self, order):
        route_point_getter = order.order_route_point
        if not route_point_getter:
            return
        delivery_route_point = route_point_getter.get_by_kind(RoutePointKind.DELIVERY)
        return delivery_route_point

    def get_planned_arrival(self, order):
        route_point = self._get_delivery_route_point(order)
        if not route_point:
            return
        return serializers.DateTimeField().to_representation(route_point.start_time)

    def get_planned_arrival_interval(self, order):
        route_point = self._get_delivery_route_point(order)
        if not route_point:
            return

        after, before = map(serializers.DateTimeField().to_representation, route_point.planned_order_arrival_interval)
        return {'upper': before, 'lower': after}


class SubManagerOrderSerializer(PublicReportSerializer):
    in_queue = serializers.IntegerField()
    eta = serializers.IntegerField(source='eta_seconds')
