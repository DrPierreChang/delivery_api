import calendar

from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction

from rest_framework import serializers

from base.api.legacy.serializers.fields import MarkdownField
from base.models import Member
from base.utils import day_in_future
from merchant.models import Label, SkillSet, SubBranding
from merchant_extension.models import ResultChecklist
from radaro_utils.serializers.fields import DurationInSecondsField
from radaro_utils.serializers.mixins import SerializerExcludeFieldsMixin
from radaro_utils.serializers.web.fields import WebPrimaryKeyWithMerchantRelatedField
from reporting.model_mapping import serializer_map
from route_optimisation.api.fields import CurrentMerchantDefault
from tasks.api.legacy.serializers.orders import METERS_IN_MILE
from tasks.api.mobile.driver_orders.v1.serializers.skill_set import OrderSkillSetsValidator
from tasks.models import Customer, Order

from ..barcode import BarcodeSerializer
from ..location import WebLocationSerializer
from .cargoe import WebOrderCargoes
from .deliver import DeliverWebOrderSerializer
from .pickup import PickupWebOrderSerializer
from .terminate import TerminateCodesSerializer
from .validators import JobIntervalsValidator
from .wayback import WaybackWebOrderSerializer


class AvatarManagerSerializer(serializers.ModelSerializer):
    url = serializers.ImageField(source='avatar', read_only=True)
    thumbnail_url = serializers.ImageField(source='thumb_avatar_100x100', read_only=True)

    class Meta:
        model = Customer
        fields = ('url', 'thumbnail_url')


class ManagerSerializer(serializers.ModelSerializer):
    avatar = AvatarManagerSerializer(source='*')
    can_make_payment = serializers.SerializerMethodField(method_name='make_payment')

    class Meta:
        model = Member
        fields = (
            'id', 'email', 'first_name', 'last_name', 'full_name', 'avatar', 'work_status', 'phone_number',
            'can_make_payment', 'merchant_position', 'role',
        )
        extra_kwargs = {'phone_number': {'source': 'phone'}}

    def make_payment(self, obj):
        if obj.is_admin:
            return True
        return False


class StatisticsWebOrderSerializer(SerializerExcludeFieldsMixin, serializers.ModelSerializer):
    distance = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField()
    assigned_at = serializers.DateTimeField()
    picked_up_at = serializers.DateTimeField()
    in_progress_at = serializers.DateTimeField()
    wayback_at = serializers.DateTimeField()
    time_at_job = DurationInSecondsField()
    time_at_pickup = DurationInSecondsField()
    duration = DurationInSecondsField()

    class Meta:
        model = Order
        fields = (
            'created_at', 'updated_at', 'started_at', 'finished_at',
            'assigned_at', 'picked_up_at', 'in_progress_at', 'wayback_at',
            'time_at_job', 'time_at_pickup', 'duration',
            'pick_up_distance', 'wayback_distance', 'distance', 'order_distance', 'statuses_time_distance',
        )

    def get_distance(self, instance):
        if hasattr(instance, 'distance') and instance.distance is not None:
            return float(instance.distance) * METERS_IN_MILE


class ChecklistSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResultChecklist
        fields = ('id', 'is_correct', 'is_passed')


class GeofenceWebOrderSerializer(serializers.ModelSerializer):
    time_inside_geofence = DurationInSecondsField()
    time_inside_pickup_geofence = DurationInSecondsField()

    class Meta:
        model = Order
        fields = (
            'pickup_geofence_entered', 'time_inside_pickup_geofence',
            'geofence_entered', 'geofence_entered_on_backend', 'time_inside_geofence',
            'is_completed_by_geofence',
        )


@serializer_map.register_serializer_for_detailed_dump(version='web')
class WebOrderSerializer(serializers.ModelSerializer):
    merchant = serializers.HiddenField(default=CurrentMerchantDefault())

    content_type = serializers.SerializerMethodField()
    external_id = serializers.SerializerMethodField(read_only=True)
    driver_id = WebPrimaryKeyWithMerchantRelatedField(
        source='driver', queryset=Member.objects.all().filter(role__in=[Member.DRIVER, Member.MANAGER_OR_DRIVER]),
        required=False, allow_null=True
    )
    description = MarkdownField(required=False, allow_blank=True)

    starting_point = WebLocationSerializer(required=False, allow_null=False, read_only=True)
    ending_point = WebLocationSerializer(required=False, allow_null=False, read_only=True)

    pickup = PickupWebOrderSerializer(source='*', required=False)
    deliver = DeliverWebOrderSerializer(source='*')
    wayback = WaybackWebOrderSerializer(source='*', read_only=True)
    completion = TerminateCodesSerializer(required=False, source='*')

    statistics = StatisticsWebOrderSerializer(source='*', read_only=True)
    geofence = GeofenceWebOrderSerializer(source='*', read_only=True)

    manager = ManagerSerializer(read_only=True)
    sub_branding_id = WebPrimaryKeyWithMerchantRelatedField(
        source='sub_branding', queryset=SubBranding.objects.all(), required=False, allow_null=True
    )

    checklist = ChecklistSerializer(source='driver_checklist', read_only=True)
    label_ids = WebPrimaryKeyWithMerchantRelatedField(
        many=True, source='labels', queryset=Label.objects.all(), required=False
    )
    skill_set_ids = WebPrimaryKeyWithMerchantRelatedField(
        many=True, source='skill_sets', queryset=SkillSet.objects.all(), required=False
    )
    barcodes = BarcodeSerializer(many=True, required=False)
    cargoes = WebOrderCargoes(source='*', read_only=True)

    sort_rate = serializers.SerializerMethodField()
    is_archived = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'merchant',
            'content_type', 'id', 'order_id', 'external_id', 'driver_id', 'concatenated_order_id',
            'title', 'description', 'comment', 'customer_comment',
            'starting_point', 'ending_point',
            'pickup', 'deliver', 'wayback', 'statistics', 'geofence',
            'status', 'manager', 'merchant_id', 'sub_branding_id',
            'completion', 'checklist', 'label_ids', 'skill_set_ids', 'barcodes', 'cargoes',
            'is_confirmed_by_customer', 'customer_review_opt_in',
            'sort_rate', 'public_report_link', 'is_archived',
            'capacity', 'deleted', 'rating', 'cost',
            'deadline_passed', 'changed_in_offline', 'external_job_id', 'model_prototype_id',
            'customer_survey_id',
        )
        editable_fields = {
            'title', 'description', 'comment', 'driver_id', 'pickup', 'deliver', 'status', 'sub_branding_id',
            'label_ids', 'skill_set_ids', 'barcodes', 'capacity',
        }
        read_only_fields = list(set(fields) - set(editable_fields))
        validators = [OrderSkillSetsValidator(), JobIntervalsValidator()]

    def __init__(self, instance=None, *args, **kwargs):
        super().__init__(instance, *args, **kwargs)
        self.remove_disabled_fields(self.get_merchant())
        self.day_in_future = day_in_future()

    def remove_disabled_fields(self, merchant):
        if not merchant.enable_job_description:
            self.fields.pop('description')
        if not merchant.use_subbranding:
            self.fields.pop('sub_branding_id')
        if not merchant.enable_labels:
            self.fields.pop('label_ids')
        if not merchant.enable_skill_sets:
            self.fields.pop('skill_set_ids')
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

        self.day_in_future = day_in_future()

    def get_merchant(self):
        if isinstance(self.instance, models.Manager):
            order = self.instance.all().first()
            if order is not None:
                return order.merchant

        if isinstance(self.instance, Order):
            return self.instance.merchant

        if 'request' in self.context and self.context['request'] is not None:
            user = self.context['request'].user
            if user.is_authenticated and user.current_merchant_id is not None:
                return user.current_merchant

        raise ValueError('WebOrderSerializer cannot get merchant object')

    def get_content_type(self, instance):
        return ContentType.objects.get_for_model(Order, for_concrete_model=False).model

    def get_external_id(self, instance):
        return instance.external_job.external_id if instance.external_job else None

    def get_sort_rate(self, instance):
        if hasattr(instance, 'sort_rate'):
            return instance.sort_rate
        if instance.status in Order.status_groups.UNFINISHED:
            return -self.day_in_future + Order.status_rates[instance.status]
        return -calendar.timegm(instance.updated_at.timetuple())

    def get_is_archived(self, instance):
        if hasattr(instance, 'archived'):
            return instance.archived
        return False

    def validate_status(self, new_status):
        if self.instance:
            if new_status == Order.PICK_UP and not self.instance.pickup_address:
                raise serializers.ValidationError('You cannot use pick up status', code='invalid_status')

            current_status = self.instance.status
            if current_status == new_status:
                return new_status

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
        else:
            if 'driver' in attrs:
                attrs['status'] = Order.ASSIGNED
            else:
                attrs['status'] = Order.NOT_ASSIGNED

        merchant = self.get_merchant()
        if merchant.enable_job_capacity:
            self._validate_capacity(attrs.get('capacity'), attrs.get('driver'))

        return attrs

    def _validate_capacity(self, new_job_capacity, new_driver):
        if not new_job_capacity and not new_driver:
            return

        job_capacity = new_job_capacity or self.instance.capacity if self.instance else None
        driver = new_driver or self.instance.driver if self.instance else None
        car_capacity = driver.car.capacity if driver else None

        if job_capacity and car_capacity and job_capacity > car_capacity:
            raise serializers.ValidationError(
                {'capacity': 'Forbidden to assign job since car capacity is less than job capacity.'}
            )

    def create(self, validated_data):
        barcodes = validated_data.pop('barcodes', [])
        validated_data['manager'] = self.context['request'].user

        with transaction.atomic():
            if 'pickup' in validated_data:
                pickup = self.fields['pickup'].fields['customer']
                validated_data['pickup'] = pickup.create(validated_data['pickup'])
            if 'pickup_address' in validated_data:
                pickup_address = self.fields['pickup'].fields['address']
                validated_data['pickup_address'] = pickup_address.create(validated_data['pickup_address'])
            if 'customer' in validated_data:
                customer = self.fields['deliver'].fields['customer']
                validated_data['customer'] = customer.create(validated_data['customer'])
            if 'deliver_address' in validated_data:
                deliver_address = self.fields['deliver'].fields['address']
                validated_data['deliver_address'] = deliver_address.create(validated_data['deliver_address'])

            order = super().create(validated_data)
            if barcodes:
                self.fields['barcodes'].create(list(map(lambda barcode: {'order': order, **barcode}, barcodes)))

        return order

    def update(self, instance, validated_data):
        barcodes = validated_data.pop('barcodes', [])

        with transaction.atomic():
            if 'pickup' in validated_data:
                pickup = self.fields['pickup'].fields['customer']
                validated_data['pickup'] = pickup.update(instance.pickup, validated_data['pickup'])
            if 'pickup_address' in validated_data:
                pickup_address = self.fields['pickup'].fields['address']
                validated_data['pickup_address'] = pickup_address.update(
                    instance.pickup_address, validated_data['pickup_address'])
            if 'customer' in validated_data:
                customer = self.fields['deliver'].fields['customer']
                validated_data['customer'] = customer.update(
                    instance.customer, validated_data['customer'])
            if 'deliver_address' in validated_data:
                deliver_address = self.fields['deliver'].fields['address']
                validated_data['deliver_address'] = deliver_address.update(
                    instance.deliver_address, validated_data['deliver_address'])

            order = super().update(instance, validated_data)
            if barcodes:
                self.fields['barcodes'].update(
                    instance.barcodes.all(),
                    list(map(lambda barcode: {'order': order, **barcode}, barcodes))
                )

        return order
