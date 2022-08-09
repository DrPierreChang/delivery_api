from django.db import transaction
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from base.models import Member
from merchant.api.mobile.skill_sets.v1.serializers import SkillSetSerializer
from merchant.models import Label, SkillSet, SubBranding
from merchant_extension.api.mobile.checklists.v1.serializers import JobChecklistSerializer
from radaro_utils.serializers.mixins import SerializerExcludeFieldsMixin
from radaro_utils.serializers.mobile.fields import RadaroMobilePrimaryKeyWithMerchantRelatedField
from radaro_utils.serializers.mobile.serializers import RadaroMobileModelSerializer
from tasks.api.web.orders.serializers.order.validators import JobIntervalsValidator
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

from .....customers.v1.serializers import CustomerSerializer, PickupCustomerSerializer
from .....fields.v1 import CurrentMerchantDefault
from ..barcodes import BarcodeSerializer
from ..fields import MarkdownField
from ..label import LabelSerializer
from ..location import OrderLocationSerializer
from ..skill_set import OrderSkillSetsValidator
from .cargoes import DriverOrderCargoes
from .confirmation import ConfirmationOrderMixinSerializer, StatusByConfirmationValidator
from .offline import OfflineOrderMixinSerializer
from .terminate import TerminateOrderMixinSerializer


class PickupStatusValidator:
    instance = None
    user = None

    def set_context(self, serializer_field):
        self.instance = getattr(serializer_field.root, 'instance', None)

    def __call__(self, new_status):
        if self.instance:
            if new_status in [OrderStatus.PICK_UP, OrderStatus.PICKED_UP] and not self.instance.pickup_address:
                raise serializers.ValidationError(_('You cannot use pick up status'), code='invalid_status')


class StatusValidator:
    instance = None
    user = None

    def set_context(self, serializer_field):
        self.instance = getattr(serializer_field.root, 'instance', None)
        self.user = serializer_field.root.context['request'].user

    def __call__(self, new_status):
        if self.instance:
            current_status = self.instance.status
            if current_status == new_status:
                return

            available_statuses = self.instance.current_available_statuses_for_user(current_status, self.user)
            if new_status not in available_statuses:
                raise serializers.ValidationError(
                    _('Forbidden to change status from "{old_status}" to "{new_status}"'
                      .format(old_status=current_status, new_status=new_status)),
                    code='invalid_status',
                )


class OrderDataByStatusValidator:
    instance = None

    def set_context(self, serializer):
        self.instance = getattr(serializer, 'instance', None)

    def __call__(self, attrs):
        status = attrs.get('status', self.instance.status if self.instance else None)

        if 'starting_point' in attrs:
            if status not in [OrderStatus.PICK_UP, OrderStatus.IN_PROGRESS]:
                raise serializers.ValidationError(
                    {'starting_point': _('You cannot send starting point in the current status')},
                    code='invalid_status_for_starting_point',
                )

        if 'ending_point' in attrs:
            if status not in [OrderStatus.FAILED, OrderStatus.DELIVERED]:
                raise serializers.ValidationError(
                    {'ending_point': _('You cannot send ending point in the current status')},
                    code='invalid_status_for_ending_point',
                )

        if 'wayback_point' in attrs:
            if status != OrderStatus.WAY_BACK:
                raise serializers.ValidationError(
                    {'wayback_point': _('You cannot specify a wayback point in the current status')},
                    code='invalid_status_for_wayback_point',
                )


class SubBrandingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubBranding
        fields = ('id', 'name', 'logo')


class PlannedArrivalSerializer(serializers.Serializer):
    after = serializers.DateTimeField(source='planned_arrival_after')
    before = serializers.DateTimeField(source='planned_arrival_before')


class PlannedTimesSerializer(serializers.Serializer):
    planned_arrival = PlannedArrivalSerializer(source='*')
    planned_time = serializers.DateTimeField(source='planned_arrival')


class QueueSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    all = serializers.IntegerField()


class RODetailsSerializer(serializers.Serializer):
    pickup = PlannedTimesSerializer(allow_null=True)
    delivery = PlannedTimesSerializer(allow_null=True)
    queue = QueueSerializer(allow_null=True)


class DriverOrderSerializer(OfflineOrderMixinSerializer,
                            TerminateOrderMixinSerializer,
                            ConfirmationOrderMixinSerializer,
                            SerializerExcludeFieldsMixin,
                            RadaroMobileModelSerializer):
    merchant = serializers.HiddenField(default=CurrentMerchantDefault())
    manager = serializers.HiddenField(default=serializers.CurrentUserDefault())

    server_entity_id = serializers.IntegerField(source='id', read_only=True)
    external_id = serializers.SerializerMethodField(read_only=True)
    driver_id = RadaroMobilePrimaryKeyWithMerchantRelatedField(
        source='driver',
        queryset=Member.all_drivers.all().not_deleted(),
        required=False,
        write_only=True,
    )

    description = MarkdownField(required=False, allow_blank=True)
    pickup_address = OrderLocationSerializer(required=False, allow_null=True)
    deliver_address = OrderLocationSerializer(required=True)
    wayback_point = OrderLocationSerializer(required=False, allow_null=True)
    starting_point = OrderLocationSerializer(required=False, allow_null=False, write_only=True)
    ending_point = OrderLocationSerializer(required=False, allow_null=False, write_only=True)

    customer = CustomerSerializer(required=True)
    pickup = PickupCustomerSerializer(required=False, allow_null=True)

    sub_branding = SubBrandingSerializer(read_only=True)
    sub_branding_id = RadaroMobilePrimaryKeyWithMerchantRelatedField(
        source='sub_branding',
        queryset=SubBranding.objects.all(),
        required=False,
        write_only=True,
    )
    labels = LabelSerializer(read_only=True, many=True)
    label_ids = RadaroMobilePrimaryKeyWithMerchantRelatedField(
        source='labels',
        queryset=Label.objects.all(),
        required=False,
        write_only=True,
        many=True,
    )
    checklist = JobChecklistSerializer(source='driver_checklist', read_only=True)
    skill_sets = SkillSetSerializer(read_only=True, many=True)
    skill_set_ids = RadaroMobilePrimaryKeyWithMerchantRelatedField(
        source='skill_sets',
        queryset=SkillSet.objects.all(),
        required=False,
        write_only=True,
        many=True,
    )
    barcodes = BarcodeSerializer(required=False, many=True)
    cargoes = DriverOrderCargoes(source='*', required=False)
    statuses_time_distance = serializers.SerializerMethodField()

    ro_details = RODetailsSerializer(source='route_optimisation_details', read_only=True)

    pickup_geofence_entered = serializers.SerializerMethodField()
    geofence_entered = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'server_entity_id', 'order_id', 'driver_id', 'external_id', 'title', 'description',
            'pickup_after', 'pickup_before', 'deliver_after', 'deliver_before',
            'pickup_address', 'deliver_address', 'wayback_point', 'starting_point', 'ending_point',
            'customer', 'pickup', 'comment', 'status',
            'started_at', 'picked_up_at', 'in_progress_at', 'wayback_at', 'finished_at', 'updated_at',
            'is_confirmed_by_customer', 'pre_confirmation',
            'confirmation', 'pick_up_confirmation', 'completion', 'statuses_time_distance', 'sub_branding_id',
            'sub_branding', 'checklist', 'labels', 'skill_sets', 'barcodes', 'label_ids', 'skill_set_ids',
            'merchant', 'manager', 'cargoes', 'offline_happened_at', 'ro_details',
            'pickup_geofence_entered', 'geofence_entered', 'concatenated_order_id',
        ]
        editable_fields = {'status', 'pre_confirmation', 'confirmation', 'pick_up_confirmation', 'completion',
                           'wayback_point', 'starting_point', 'ending_point'}
        read_only_fields = list(set(fields) - set(editable_fields))
        validators = [OrderDataByStatusValidator(), OrderSkillSetsValidator(),
                      JobIntervalsValidator(), StatusByConfirmationValidator()]
        extra_kwargs = {
            'status': {'validators': [StatusValidator(), PickupStatusValidator()]},
        }

    def get_external_id(self, instance):
        return instance.external_job.external_id if instance.external_job else None

    def get_pickup_geofence_entered(self, instance):
        return instance.pickup_geofence_entered or False

    def get_geofence_entered(self, instance):
        return instance.geofence_entered or False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        merchant = self.context['request'].user.current_merchant
        if not merchant.enable_job_description:
            self.fields.pop('description')
        if not merchant.use_pick_up_status:
            self.fields.pop('pickup_after')
            self.fields.pop('pickup_before')
            self.fields.pop('pickup_address')
            self.fields.pop('pickup')
            self.fields.pop('picked_up_at')
        if not merchant.use_way_back_status:
            self.fields.pop('wayback_point')
            self.fields.pop('wayback_at')
        if not merchant.use_subbranding:
            self.fields.pop('sub_branding')
            self.fields.pop('sub_branding_id')
        if not merchant.enable_labels:
            self.fields.pop('labels')
            self.fields.pop('label_ids')
        if not merchant.enable_skill_sets:
            self.fields.pop('skill_sets')
            self.fields.pop('skill_set_ids')
        if merchant.option_barcodes == merchant.TYPES_BARCODES.disable:
            self.fields.pop('barcodes')
        if not merchant.enable_skids:
            self.fields.pop('cargoes')
        if not merchant.enable_concatenated_orders:
            self.fields.pop('concatenated_order_id')

        if not (isinstance(self.instance, Order) and not self.instance.starting_point_id):
            self.fields['starting_point'].read_only = True

    def get_statuses_time_distance(self, instance):
        statuses_time_distance = instance.statuses_time_distance
        if not any(statuses_time_distance.values()):
            return None
        return statuses_time_distance

    def validate(self, attrs):
        if self.instance:
            if 'status' in attrs:
                driver = self.instance.driver
                if attrs['status'] == Order.NOT_ASSIGNED and driver:
                    attrs['driver'] = None
                if attrs['status'] != Order.NOT_ASSIGNED and not driver:
                    attrs['driver'] = self.context['request'].user
        else:
            if 'driver' in attrs:
                attrs['status'] = Order.ASSIGNED
            else:
                attrs['status'] = Order.NOT_ASSIGNED

        attrs = super().validate(attrs)
        return attrs

    def update(self, instance, validated_data):
        with transaction.atomic():
            if 'wayback_point' in validated_data:
                wayback_field = self.fields['wayback_point']
                validated_data['wayback_point'] = wayback_field.create(validated_data['wayback_point'])
            if 'starting_point' in validated_data:
                starting_field = self.fields['starting_point']
                validated_data['starting_point'] = starting_field.create(validated_data['starting_point'])
            if 'ending_point' in validated_data:
                ending_field = self.fields['ending_point']
                validated_data['ending_point'] = ending_field.create(validated_data['ending_point'])
            order = super().update(instance, validated_data)

        if validated_data.get('status', None) == order.DELIVERED:
            order.handle_confirmation()
        if validated_data.get('terminate_codes', None):
            order.handle_termination_code()
        return order
