from __future__ import unicode_literals

from collections import OrderedDict
from itertools import chain

from rest_framework import serializers

from base.api.legacy.serializers.fields import MarkdownField
from driver.api.legacy.serializers.driver import DriverSerializer
from merchant.api.legacy.serializers import (
    HubSerializerV2,
    LabelHexSerializer,
    MerchantSerializer,
    SkillSetSerializer,
    SubBrandingSerializer,
)
from routing.serializers.fields import LatLngLocation

from .core import (
    BaseOrderSerializer,
    OrderConfirmationPhotoSerializer,
    OrderLocationSerializerV2,
    OrderPreConfirmationPhotoSerializer,
)
from .customers import CustomerSerializer, PickupSerializer
from .documents import OrderConfirmationDocumentSerializer

VALID_MILES_TO_HUB = 0.63


class PublicOrderSerializer(BaseOrderSerializer):
    customer = CustomerSerializer()
    description = MarkdownField(allow_blank=True, allow_null=True, required=False)
    pickup = PickupSerializer()
    pickup_address = OrderLocationSerializerV2()
    deliver_address = OrderLocationSerializerV2()
    starting_point = OrderLocationSerializerV2()
    in_progress_point = serializers.SerializerMethodField()
    wayback_point = OrderLocationSerializerV2()
    wayback_hub = HubSerializerV2()
    assigned_at = serializers.DateTimeField(read_only=True)
    wayback_at = serializers.DateTimeField(read_only=True)
    ending_point = OrderLocationSerializerV2()
    order_confirmation_photos = OrderConfirmationPhotoSerializer(many=True, read_only=True)
    pre_confirmation_photos = OrderPreConfirmationPhotoSerializer(many=True, read_only=True)
    pick_up_confirmation_photos = OrderConfirmationPhotoSerializer(many=True, read_only=True)
    order_confirmation_documents = OrderConfirmationDocumentSerializer(many=True, read_only=True)
    statuses_time_distance = serializers.DictField(read_only=True)
    real_path = serializers.SerializerMethodField()
    real_path_dict = serializers.DictField(source='real_path')

    class Meta(BaseOrderSerializer.Meta):
        fields = (
            'id', 'title', 'order_id', 'deliver_after', 'deliver_before', 'status',
            'ending_point', 'starting_point', 'in_progress_point',
            'pickup_after', 'pickup_before', 'pickup_address', 'pickup_address_2', 'pickup',
            'deliver_address', 'deliver_address_2',
            'wayback_point', 'wayback_hub', 'wayback_at',
            'assigned_at', 'finished_at', 'started_at', 'picked_up_at', 'in_progress_at',
            'order_distance', 'real_path', 'real_path_dict', 'terminate_codes', 'description',
            'pre_confirmation_signature', 'confirmation_signature',
            'pre_confirmation_photos', 'order_confirmation_photos',
            'order_confirmation_documents',
            'confirmation_comment', 'pre_confirmation_comment',
            'pick_up_confirmation_signature', 'pick_up_confirmation_photos', 'pick_up_confirmation_comment',
            'terminate_comment', 'comment', 'duration', 'time_at_job',
            'changed_in_offline', 'created_at',
            'is_confirmed_by_customer', 'customer', 'rating', 'customer_comment',
            'pick_up_distance', 'wayback_distance', 'public_report_link', 'statuses_time_distance',
            'barcodes', 'cargoes',
        )
        exclude = ()

    def get_real_path(self, instance):
        if instance.real_path is None:
            return

        real_path = OrderedDict((status, instance.real_path.get(status, []))
                                for status in (instance.PICK_UP, instance.IN_PROGRESS, instance.WAY_BACK))
        return list(chain.from_iterable(real_path.values())) or instance.real_path.get('full', [])

    def get_in_progress_point(self, instance):
        return {'location': LatLngLocation().to_representation(instance.in_progress_point)} \
            if instance.in_progress_point else None


class PublicSubBrandingSerializer(SubBrandingSerializer):
    class Meta(SubBrandingSerializer.Meta):
        fields = ('name',)


class PublicSkillSetSerializer(SkillSetSerializer):
    class Meta(SkillSetSerializer.Meta):
        fields = ('name', 'color', 'is_secret', 'description')


class PublicMerchantSerializer(MerchantSerializer):
    enable_barcode_before_delivery = serializers.BooleanField()
    enable_barcode_after_delivery = serializers.BooleanField()

    class Meta(MerchantSerializer.Meta):
        fields = ('date_format', 'use_success_codes', 'distance_show_in', 'enable_labels', 'enable_skill_sets',
                  'enable_skids', 'name', 'use_subbranding', 'option_barcodes', 'deliver_address_2_enabled',
                  'enable_barcode_before_delivery', 'enable_barcode_after_delivery',
                  'enable_delivery_confirmation_documents', 'language',)


class PublicDriverSerializer(DriverSerializer):
    class Meta(DriverSerializer.Meta):
        fields = ('avatar', 'phone', 'full_name',)


class PublicHubSerializer(HubSerializerV2):
    class Meta(HubSerializerV2.Meta):
        fields = ('location', 'name', )


class PublicReportSerializer(serializers.Serializer):
    order = serializers.SerializerMethodField()
    merchant = PublicMerchantSerializer()
    driver = PublicDriverSerializer()
    sub_branding = PublicSubBrandingSerializer()
    assigned_time = serializers.DateTimeField(source='assigned_at')
    wayback_time = serializers.DateTimeField(source='wayback_at')
    hub = serializers.SerializerMethodField()
    labels = LabelHexSerializer(many=True)
    skill_sets = PublicSkillSetSerializer(many=True)

    def get_order(self, order):
        return PublicOrderSerializer(order).data

    def get_hub(self, order):
        nearest_hub = None
        if order.ending_point:
            hubs_qs = order.merchant.hub_set.all().select_related('location')
            nearest_hub = hubs_qs.order_by_distance(*order.ending_point.coordinates).first()
        if nearest_hub and nearest_hub.distance < VALID_MILES_TO_HUB:
            return PublicHubSerializer(nearest_hub).data
