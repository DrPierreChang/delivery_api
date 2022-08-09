from rest_framework import serializers

from tasks.api.mobile.driver_orders.v1.serializers import OrderLocationSerializer
from tasks.models import ConcatenatedOrder, Order


class OrderSerializer(serializers.ModelSerializer):
    external_id = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ('order_id', 'external_id')

    def get_external_id(self, instance):
        return instance.external_job.external_id if instance.external_job else None


class ExternalConcatenatedOrderSerializer(serializers.ModelSerializer):
    orders = OrderSerializer(many=True, read_only=True)
    deliver_address = OrderLocationSerializer()

    class Meta:
        model = ConcatenatedOrder
        fields = (
            'order_id', 'driver_id', 'deliver_day', 'customer', 'deliver_address', 'deliver_before', 'deliver_after',
            'status', 'merchant_id', 'orders',
        )


class ExternalConcatenatedOrderEventsSerializer(serializers.Serializer):
    updated_at = serializers.DateTimeField()
    concatenated_order_info = ExternalConcatenatedOrderSerializer()
    token = serializers.CharField(max_length=255)
    topic = serializers.CharField(max_length=128)
