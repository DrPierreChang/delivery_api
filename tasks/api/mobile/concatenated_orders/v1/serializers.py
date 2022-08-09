from django.db import transaction
from django.db.models import Prefetch, prefetch_related_objects
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from base.models import Member
from merchant.api.mobile.skill_sets.v1.serializers import SkillSetSerializer
from merchant_extension.api.mobile.checklists.v1.serializers import JobChecklistSerializer
from radaro_utils.serializers.mobile.fields import RadaroMobilePrimaryKeyWithMerchantRelatedField
from radaro_utils.serializers.mobile.serializers import RadaroMobileListSerializer, RadaroMobileModelSerializer
from reporting.context_managers import track_fields_on_change
from tasks.mixins.order_status import OrderStatus
from tasks.models import Barcode, ConcatenatedOrder, Order

from ...customers.v1.serializers import CustomerSerializer, PickupCustomerSerializer
from ...driver_orders.v1.serializers import (
    ConfirmationOrderMixinSerializer,
    DriverOrderSerializer,
    OfflineOrderMixinSerializer,
    OrderDataByStatusValidator,
    OrderLocationSerializer,
    ScanBarcodesSerializer,
    StatusByConfirmationValidator,
    StatusValidator,
    TerminateOrderMixinSerializer,
)
from ...driver_orders.v1.serializers.label import LabelSerializer
from ...driver_orders.v1.serializers.order.geofence import OrderGeofenceSerializer, OrderGeofenceStatusValidator


class ConcatenatedPickupStatusValidator:
    instance = None

    def set_context(self, serializer_field):
        self.instance = getattr(serializer_field.root, 'instance', None)

    def __call__(self, new_status):
        if self.instance and new_status in [OrderStatus.PICK_UP, OrderStatus.PICKED_UP]:
            if not self.instance.orders.all().filter(pickup_address__isnull=False).exists():
                raise serializers.ValidationError(_('You cannot use pick up status'), code='invalid_status')


class PickupsDriverConcatenatedOrderSerializer(serializers.Serializer):
    pickup_address = OrderLocationSerializer()
    pickup = PickupCustomerSerializer()

    class Meta:
        list_serializer_class = RadaroMobileListSerializer


class DriverConcatenatedOrderSerializer(OfflineOrderMixinSerializer,
                                        TerminateOrderMixinSerializer,
                                        ConfirmationOrderMixinSerializer,
                                        RadaroMobileModelSerializer):
    server_entity_id = serializers.IntegerField(source='id', read_only=True)
    driver_id = RadaroMobilePrimaryKeyWithMerchantRelatedField(
        source='driver',
        queryset=Member.all_drivers.all().not_deleted(),
        required=False,
        write_only=True,
    )

    pickups = PickupsDriverConcatenatedOrderSerializer(many=True)
    pickup_after = serializers.DateTimeField(source='pickup_interval.after')
    pickup_before = serializers.DateTimeField(source='pickup_interval.before')
    deliver_address = OrderLocationSerializer(required=True)
    wayback_point = OrderLocationSerializer(required=False, allow_null=True)
    starting_point = OrderLocationSerializer(required=False, allow_null=False, write_only=True)
    ending_point = OrderLocationSerializer(required=False, allow_null=False, write_only=True)
    customer = CustomerSerializer(required=True)
    labels = LabelSerializer(read_only=True, many=True)
    checklist = JobChecklistSerializer(source='driver_checklist', read_only=True)
    skill_sets = SkillSetSerializer(read_only=True, many=True)
    orders = serializers.SerializerMethodField()

    class Meta:
        model = ConcatenatedOrder
        fields = [
            'server_entity_id', 'order_id', 'driver_id',
            'deliver_after', 'deliver_before',
            'pickups', 'pickup_after', 'pickup_before',
            'deliver_address', 'starting_point', 'ending_point', 'wayback_point',
            'customer', 'comment', 'status',
            'started_at', 'picked_up_at', 'in_progress_at', 'wayback_at', 'finished_at', 'updated_at',
            'is_confirmed_by_customer',
            'pick_up_confirmation', 'pre_confirmation', 'confirmation', 'completion', 'offline_happened_at',
            'labels', 'checklist', 'skill_sets', 'geofence_entered', 'orders',
        ]
        editable_fields = {
            'status', 'pre_confirmation', 'confirmation', 'completion',
            'wayback_point', 'starting_point', 'ending_point',
        }
        read_only_fields = list(set(fields) - set(editable_fields))
        validators = [OrderDataByStatusValidator(), StatusByConfirmationValidator()]
        extra_kwargs = {
            'status': {'validators': [StatusValidator(), ConcatenatedPickupStatusValidator()]},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        merchant = self.context['request'].user.current_merchant
        if not merchant.use_pick_up_status:
            self.fields.pop('pickups')
            self.fields.pop('pickup_after')
            self.fields.pop('pickup_before')
            self.fields.pop('picked_up_at')
        if not merchant.use_way_back_status:
            self.fields.pop('wayback_point')
            self.fields.pop('wayback_at')

        if self.instance and (isinstance(self.instance, list) or self.instance.starting_point_id):
            self.fields['starting_point'].read_only = True

    def get_orders(self, instance):
        return DriverOrderSerializer(
            instance.orders.all(), many=True,
            context=self.context, exclude_fields=('checklist',)
        ).data

    def validate(self, attrs):
        if 'status' in attrs:
            driver = self.instance.driver
            if attrs['status'] == OrderStatus.NOT_ASSIGNED and driver:
                attrs['driver'] = None
            if attrs['status'] != OrderStatus.NOT_ASSIGNED and not driver:
                attrs['driver'] = self.context['request'].user

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
            concatenated_order = super().update(instance, validated_data)

        if validated_data.get('status', None) == OrderStatus.DELIVERED:
            concatenated_order.handle_confirmation()
        if validated_data.get('terminate_codes', None):
            concatenated_order.handle_termination_code()
        return concatenated_order

    @property
    def data(self):
        """After updating the object, the prefetch is cleared, for performance it needs to be loaded back."""
        if not hasattr(self.instance, '_prefetched_objects_cache'):
            prefetch_related_objects(
                [self.instance],
                Prefetch('orders', queryset=Order.objects.all().prefetch_for_mobile_api().order_inside_concatenated())
            )
        return super().data


class ScanBarcodesConcatenatedOrderSerializer(ScanBarcodesSerializer):

    def scan_barcode_concatenated_order(self):
        codes = self.validated_data['barcode_codes']
        concatenated_order = self.instance
        barcodes = Barcode.objects.merchant_active_barcodes(concatenated_order.merchant)
        barcodes = barcodes.filter(order__concatenated_order=concatenated_order, code_data__in=codes)

        if codes:
            with track_fields_on_change(list(concatenated_order.orders.all()), initiator=self.context['request'].user):
                if concatenated_order.status in (OrderStatus.ASSIGNED, OrderStatus.PICKED_UP, OrderStatus.PICK_UP):
                    barcodes.update(scanned_at_the_warehouse=True)
                if concatenated_order.status == OrderStatus.IN_PROGRESS:
                    barcodes.update(scanned_upon_delivery=True)

        if self.validated_data.get('changed_in_offline'):
            concatenated_order.changed_in_offline = True
            concatenated_order.save()

        return concatenated_order.orders.all()


class ConcatenatedOrderGeofenceStatusValidator(OrderGeofenceStatusValidator):
    allowed_statuses = (OrderStatus.IN_PROGRESS, )


class ConcatenatedOrderGeofenceSerializer(OrderGeofenceSerializer):
    geofence_entered = serializers.BooleanField(required=True, allow_null=False,
                                                validators=[ConcatenatedOrderGeofenceStatusValidator()])
