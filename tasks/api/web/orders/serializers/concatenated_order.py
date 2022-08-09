from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Prefetch, prefetch_related_objects

from rest_framework import serializers

from base.models import Member
from radaro_utils.serializers.web.fields import WebPrimaryKeyWithMerchantRelatedField
from reporting.model_mapping import serializer_map
from tasks.api.mobile.driver_orders.v1.serializers.skill_set import OrderSkillSetsValidator
from tasks.models import ConcatenatedOrder, Order

from .customer import CustomerSerializer
from .location import WebLocationSerializer
from .order import ChecklistSerializer, WebOrderSerializer
from .order.pickup import PickupCustomerSerializer
from .order.terminate import TerminateCodeNumberSerializer


class DeliverConcatenatedOrderSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer()
    address = WebLocationSerializer(source='deliver_address')

    class Meta:
        model = ConcatenatedOrder
        fields = ('customer', 'address', 'before', 'after')
        extra_kwargs = {
            'before': {'source': 'deliver_before'},
            'after': {'source': 'deliver_after'},
        }


class StatisticsConcatenatedOrderSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField()
    assigned_at = serializers.DateTimeField()
    picked_up_at = serializers.DateTimeField()
    in_progress_at = serializers.DateTimeField()
    wayback_at = serializers.DateTimeField()

    class Meta:
        model = ConcatenatedOrder
        fields = (
            'created_at', 'updated_at', 'started_at', 'finished_at',
            'assigned_at', 'picked_up_at', 'in_progress_at', 'wayback_at',
        )


class PickupsConcatenatedOrderSerializer(serializers.Serializer):
    customer = PickupCustomerSerializer(source='pickup')
    address = WebLocationSerializer(source='pickup_address')
    before = serializers.DateTimeField(source='pickup_before')
    after = serializers.DateTimeField(source='pickup_after')


@serializer_map.register_serializer_for_detailed_dump(version='web')
@serializer_map.register_serializer_for_detailed_dump(version=2)
@serializer_map.register_serializer_for_detailed_dump(version=1)
class ConcatenatedOrderSerializer(serializers.ModelSerializer):
    content_type = serializers.SerializerMethodField()
    deliver_day = serializers.DateField(required=False)
    pickups = PickupsConcatenatedOrderSerializer(many=True, read_only=True)
    deliver = DeliverConcatenatedOrderSerializer(source='*', required=False)
    driver_id = WebPrimaryKeyWithMerchantRelatedField(
        source='driver', queryset=Member.objects.all().filter(role__in=[Member.DRIVER, Member.MANAGER_OR_DRIVER]),
        required=False, allow_null=True
    )
    statistics = StatisticsConcatenatedOrderSerializer(source='*', read_only=True)
    checklist = ChecklistSerializer(source='driver_checklist', read_only=True)
    skill_set_ids = WebPrimaryKeyWithMerchantRelatedField(many=True, source='skill_sets', read_only=True)
    label_ids = WebPrimaryKeyWithMerchantRelatedField(many=True, source='labels', read_only=True)
    orders = serializers.SerializerMethodField()

    class Meta:
        model = ConcatenatedOrder
        fields = (
            'content_type', 'id', 'driver_id', 'deliver_day', 'pickups', 'deliver', 'status',
            'merchant_id', 'statistics', 'checklist', 'skill_set_ids', 'label_ids', 'orders',
        )
        editable_fields = {'status', 'driver_id' 'deliver'}
        read_only_fields = list(set(fields) - set(editable_fields))
        validators = [OrderSkillSetsValidator()]

    def __init__(self, instance=None, *args, **kwargs):
        super().__init__(instance, *args, **kwargs)
        if isinstance(instance, ConcatenatedOrder):
            merchant = instance.merchant
        else:
            merchant = self.context['request'].user.current_merchant

        if not merchant.use_pick_up_status:
            self.fields.pop('pickups')
        if not merchant.enable_skill_sets:
            self.fields.pop('skill_set_ids')
        if not merchant.enable_labels:
            self.fields.pop('label_ids')

    def get_content_type(self, instance):
        return ContentType.objects.get_for_model(ConcatenatedOrder, for_concrete_model=False).model

    def get_orders(self, instance):
        return WebOrderSerializer(instance.orders, many=True, context=self.context).data

    def validate_status(self, new_status):
        if self.instance:
            current_status = self.instance.status
            if current_status == new_status:
                return new_status

            if new_status in [Order.PICK_UP, Order.PICKED_UP]:
                if not self.instance.orders.all().filter(pickup_address__isnull=False).exists():
                    raise serializers.ValidationError('You cannot use pick up status', code='invalid_status')

            user = self.context['request'].user
            available_statuses = self.instance.current_available_statuses_for_user(current_status, user)
            if new_status not in available_statuses:
                raise serializers.ValidationError(
                    'Forbidden to change status from "{0}" to "{1}"'.format(current_status, new_status),
                    code='invalid_status',
                )

        return new_status

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if self.instance:
            if 'status' in attrs:
                driver = attrs.get('driver', self.instance.driver)
                if attrs['status'] == Order.NOT_ASSIGNED and driver:
                    attrs['driver'] = None
                if Order.is_driver_required_for(attrs['status']) and not driver:
                    raise serializers.ValidationError(
                        {'driver_id': 'Driver required in current status'}, code='required_driver'
                    )

            elif 'driver' in attrs:
                new_driver = attrs['driver']
                if new_driver is not None and self.instance.status == Order.NOT_ASSIGNED:
                    attrs['status'] = Order.ASSIGNED
                if new_driver is None and Order.is_driver_required_for(self.instance.status):
                    raise serializers.ValidationError(
                        {'driver_id': 'Driver required in current status'}, code='required_driver'
                    )

        return attrs

    def update(self, instance, validated_data):
        with transaction.atomic():
            if 'customer' in validated_data:
                customer = self.fields['deliver'].fields['customer']
                validated_data['customer'] = customer.update(
                    instance.customer, validated_data['customer'])
            if 'deliver_address' in validated_data:
                deliver_address = self.fields['deliver'].fields['address']
                validated_data['deliver_address'] = deliver_address.update(
                    instance.deliver_address, validated_data['deliver_address'])

            instance = super().update(instance, validated_data)

        return instance

    @property
    def data(self):
        """After updating the object, the prefetch is cleared, for performance it needs to be loaded back."""
        if not hasattr(self.instance, '_prefetched_objects_cache'):
            prefetch_related_objects(
                [self.instance],
                Prefetch('orders', queryset=Order.objects.all().prefetch_for_web_api().order_inside_concatenated())
            )
        return super().data


@serializer_map.register_serializer
class ConcatenatedOrderDeltaSerializer(serializers.ModelSerializer):
    terminate_code = TerminateCodeNumberSerializer(required=False)
    completion_codes = TerminateCodeNumberSerializer(required=False, many=True, source='terminate_codes')
    completion_comment = serializers.CharField(required=False, source='terminate_comment')
    order_ids = serializers.SerializerMethodField()

    class Meta:
        model = ConcatenatedOrder
        track_change_event = ('status', 'rating', 'geofence_entered')
        exclude = ('updated_at',)

    def get_order_ids(self, instance):
        return list(Order.all_objects.filter(concatenated_order=instance).order_by('id').values_list('id', flat=True))
