from django.contrib.auth import get_user_model

from rest_framework import serializers

from merchant.api.mobile.skill_sets.v1.serializers import SkillSetSerializer
from merchant.api.web.labels.serializers import LabelSerializer
from tasks.models import Order
from tasks.utils.order_eta import ETAToOrders

from ...mobile.driver_orders.v1.serializers import RODetailsSerializer
from ..orders.serializers import (
    DeliverWebOrderSerializer,
    PickupWebOrderSerializer,
    StatisticsWebOrderSerializer,
    WebOrderSerializer,
)


class ShortDriverAvatarSerializer(serializers.Serializer):
    url = serializers.ImageField(source='avatar')
    thumbnail_url = serializers.ImageField(source='thumb_avatar_100x100_field')


class ShortDriverSerializer(serializers.ModelSerializer):
    avatar = ShortDriverAvatarSerializer(source='*')

    class Meta:
        model = get_user_model()
        fields = ('id', 'email', 'full_name', 'phone_number', 'status', 'avatar')
        extra_kwargs = {
            'phone_number': {'source': 'phone', 'default': ''},
        }


class ListShortSubManagerOrderSerializer(serializers.ListSerializer):
    eta_dict = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.eta_dict = ETAToOrders().get_eta_many_orders(self.instance, self.context['request'].user.current_merchant)


class ShortSubManagerOrderSerializer(serializers.ModelSerializer):
    external_id = serializers.SerializerMethodField()
    driver = ShortDriverSerializer()

    pickup = PickupWebOrderSerializer(source='*', required=False, exclude_fields=['confirmation'])
    deliver = DeliverWebOrderSerializer(source='*', exclude_fields=['pre_confirmation', 'confirmation'])
    statistics = StatisticsWebOrderSerializer(source='*', exclude_fields=[
        'time_at_job', 'time_at_pickup', 'duration', 'pick_up_distance', 'wayback_distance', 'distance',
        'order_distance', 'statuses_time_distance',
    ])

    labels = LabelSerializer(many=True)

    ro_details = RODetailsSerializer(source='route_optimisation_details', read_only=True)

    in_queue = serializers.IntegerField()
    eta = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'id', 'order_id', 'external_id', 'driver', 'title', 'pickup', 'deliver', 'statistics',
            'status', 'labels', 'ro_details', 'in_queue', 'eta',
        )
        list_serializer_class = ListShortSubManagerOrderSerializer

    def get_external_id(self, order):
        return order.external_job.external_id if order.external_job else None

    def get_eta(self, order):
        return self.parent.eta_dict[order.concatenated_order_id or order.id]['value']


class SubManagerOrderSerializer(WebOrderSerializer):
    driver = ShortDriverSerializer()
    labels = LabelSerializer(many=True)
    skill_sets = SkillSetSerializer(many=True)

    ro_details = RODetailsSerializer(source='route_optimisation_details', read_only=True)

    in_queue = serializers.IntegerField()
    eta = serializers.IntegerField(source='eta_seconds')

    class Meta(WebOrderSerializer.Meta):
        fields = list(
            (set(WebOrderSerializer.Meta.fields) | {'driver', 'labels', 'skill_sets', 'in_queue', 'eta', 'ro_details'})
            - {'driver_id', 'label_ids', 'skill_set_ids'}
        )

    def remove_disabled_fields(self, merchant):
        if not merchant.enable_job_description:
            self.fields.pop('description')
        if not merchant.enable_labels:
            self.fields.pop('labels')
        if not merchant.enable_skill_sets:
            self.fields.pop('skill_sets')
        if merchant.option_barcodes == merchant.TYPES_BARCODES.disable:
            self.fields.pop('barcodes')
        if not merchant.enable_skids:
            self.fields.pop('cargoes')
        if not merchant.use_pick_up_status:
            self.fields.pop('pickup')
        if not merchant.use_way_back_status:
            self.fields.pop('wayback')
        if not merchant.enable_job_capacity:
            self.fields.pop('capacity')
        if not merchant.enable_concatenated_orders:
            self.fields.pop('concatenated_order_id')
