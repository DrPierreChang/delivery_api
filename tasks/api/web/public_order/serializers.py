from rest_framework import serializers

from merchant.api.legacy.serializers import LabelHexSerializer
from tasks.api.legacy.serializers.public_report import (
    VALID_MILES_TO_HUB,
    PublicDriverSerializer,
    PublicHubSerializer,
    PublicMerchantSerializer,
    PublicSkillSetSerializer,
    PublicSubBrandingSerializer,
)
from tasks.api.web.orders.serializers import WebOrderSerializer
from tasks.api.web.orders.serializers.other import OrderPathSerializer
from tasks.models import Order


class WebPublicOrderSerializer(serializers.ModelSerializer):
    order = serializers.SerializerMethodField()
    path = OrderPathSerializer(source='*')
    merchant = PublicMerchantSerializer()
    driver = PublicDriverSerializer()
    sub_branding = PublicSubBrandingSerializer()
    assigned_time = serializers.DateTimeField(source='assigned_at')
    wayback_time = serializers.DateTimeField(source='wayback_at')
    hub = serializers.SerializerMethodField()
    labels = LabelHexSerializer(many=True)
    skill_sets = PublicSkillSetSerializer(many=True)

    class Meta:
        model = Order
        fields = (
            'order', 'path', 'merchant', 'driver', 'sub_branding', 'assigned_time', 'wayback_time', 'hub', 'labels',
            'skill_sets',
        )

    def get_order(self, order):
        return WebOrderSerializer(order).data

    def get_hub(self, order):
        if order.ending_point:
            hubs_qs = order.merchant.hub_set.all().select_related('location')
            nearest_hub = hubs_qs.order_by_distance(*order.ending_point.coordinates).first()

            if nearest_hub and nearest_hub.distance < VALID_MILES_TO_HUB:
                return PublicHubSerializer(nearest_hub).data
