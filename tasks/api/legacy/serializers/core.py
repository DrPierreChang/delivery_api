import calendar
from collections import OrderedDict
from itertools import chain

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from base.api.legacy.serializers import DelayedTaskSerializer, UserSerializer
from base.utils import day_in_future
from driver.api.legacy.serializers.work_stats.manager import DurationInSecondsField
from merchant.api.legacy.serializers.fields import LabelPKField
from merchant.models import SubBranding
from radaro_utils.geo import AddressGeocoder
from radaro_utils.serializers.fields import Base64ImageField, ParseDateTimeField
from radaro_utils.serializers.validators import LaterThenNowValidator
from routing.google import GoogleClient
from routing.serializers import LocationSerializer
from routing.serializers.fields import LatLngLocation
from tasks.mixins.order_status import OrderStatus
from tasks.models import BulkDelayedUpload, Order, OrderConfirmationPhoto, OrderLocation
from tasks.models.orders import OrderPickUpConfirmationPhoto, OrderPreConfirmationPhoto

from .barcode import BarcodeListSerializer
from .cargoes import ManagerOrderCargoes
from .customers import BaseCustomerSerializer
from .terminate_code import ErrorCodeNumberSerializer, TerminateCodeNumberSerializer


class BaseOrderSerializer(serializers.ModelSerializer):
    exclude_manager_fields = ('merchant', 'car')

    deliver_after = ParseDateTimeField(validators=[LaterThenNowValidator()], required=False, allow_null=True)
    deliver_before = ParseDateTimeField(validators=[LaterThenNowValidator()], required=False)
    deliver_address_2 = serializers.CharField(source='deliver_address.secondary_address', read_only=True)
    pickup_address_2 = serializers.CharField(source='pickup_address.secondary_address', read_only=True)
    manager = UserSerializer(exclude_fields=exclude_manager_fields, read_only=True)
    sort_rate = serializers.SerializerMethodField()
    finished_at = serializers.DateTimeField(read_only=True)
    duration = DurationInSecondsField(read_only=True)
    time_at_job = DurationInSecondsField(read_only=True)
    terminate_codes = TerminateCodeNumberSerializer(required=False, many=True)
    terminate_code = TerminateCodeNumberSerializer(required=False, allow_null=True)
    labels = LabelPKField(required=False, many=True)
    label = LabelPKField(required=False, allow_null=True)
    error_code = ErrorCodeNumberSerializer(source='terminate_code', required=False, allow_null=True)
    error_comment = serializers.CharField(source='terminate_comment', required=False, allow_null=True, allow_blank=True)
    barcodes = BarcodeListSerializer(required=False)
    cargoes = ManagerOrderCargoes(source='*', required=False)

    class Meta:
        model = Order
        exclude = ('id', 'order_token', 'bulk', 'path', 'deadline_notified', 'serialized_track', 'actual_device', )
        read_only_fields = ('order_id', 'merchant', 'duration', 'started_at', 'created_at', 'changed_in_offline',
                            'time_at_job')

    def __init__(self, instance=None, *args, **kwargs):
        super(BaseOrderSerializer, self).__init__(instance, *args, **kwargs)
        self.day_in_future = day_in_future()

    def update(self, instance, validated_data):
        terminate_codes = validated_data.pop('terminate_codes', [])
        terminate_code = validated_data.pop('terminate_code', None)
        if not terminate_codes and terminate_code:
            terminate_codes = [terminate_code, ]
        if terminate_codes:
            instance.terminate_codes.add(*terminate_codes)
        return super(BaseOrderSerializer, self).update(instance, validated_data)

    def get_sort_rate(self, instance):
        return getattr(instance, 'sort_rate', -self.day_in_future + Order.status_rates[instance.status]
                       if instance.status in OrderStatus.status_groups.UNFINISHED
                       else -calendar.timegm(instance.updated_at.timetuple()))

    def validate(self, attrs):
        driver = attrs.get('driver')
        assigned = driver and attrs.get('status') == OrderStatus.ASSIGNED
        if assigned:
            job_capacity = attrs.get('capacity', self.instance.capacity if self.instance else None)
            self._validate_capacity_for_driver(job_capacity, driver)
        return attrs

    def _validate_capacity_for_driver(self, job_capacity, driver):
        car_capacity = driver.car.capacity
        if job_capacity and car_capacity and job_capacity > car_capacity:
            raise serializers.ValidationError(
                {'capacity': 'Forbidden to assign job since car capacity is less than job capacity.'}
            )

    def validate_barcodes(self, attr):
        user = self.context.get('request').user
        if user.current_merchant.option_barcodes == user.current_merchant.TYPES_BARCODES.disable:
            raise ValidationError('Barcodes are not enabled for your merchant, '
                                  'please contact the administrator.')
        return attr

    def validate_pickup(self, pickup):
        if pickup is None and self.instance \
                and (self.instance.status == OrderStatus.PICK_UP
                     or self.instance.events.all().filter(field='status', new_value=OrderStatus.PICK_UP).exists()):
            raise ValidationError('You can\'t remove pickup, pick up status already passed')
        return pickup

    def validate_pickup_address(self, address):
        if address is None and self.instance and self.instance.pickup_address is not None:
            if self.instance.status == OrderStatus.PICK_UP \
                    or self.instance.events.all().filter(field='status', new_value=OrderStatus.PICK_UP).exists():
                raise ValidationError('You can\'t remove pickup_address, pick up status already passed')
        return address

    def validate_status(self, new_status):
        user = self.context.get('request').user
        invalid_status_error = 'Forbidden to change status from ' \
                               '"status":"{from_}" to "status":"{to_}"'
        if self.instance:
            current_status = self.instance.status
            if current_status == new_status:
                error_msg = 'Job has been already marked as {status}'.format(status=new_status)
                raise ValidationError(error_msg)

            available_statuses = self.instance.current_available_statuses_for_user(current_status, user)
            if new_status not in available_statuses:
                error_msg = invalid_status_error.format(from_=current_status, to_=new_status)
                raise ValidationError(error_msg)
            if new_status == OrderStatus.PICK_UP and self.instance.pickup_address is None:
                raise ValidationError('You can\'t set status {} for order without pick up address'
                                      .format(OrderStatus.PICK_UP))

            assign_driver_to_order = new_status == Order.ASSIGNED
            unassigned_driver_from_order = new_status == Order.NOT_ASSIGNED
            if assign_driver_to_order and user and user.is_driver:
                self._validate_capacity_for_driver(self.instance.capacity, user)
                self.instance.driver = user
            elif unassigned_driver_from_order:
                self.instance.driver = None

        elif new_status not in (Order.NOT_ASSIGNED, Order.ASSIGNED):
            error_msg = invalid_status_error.format(from_=Order.NOT_ASSIGNED, to_=new_status)
            raise ValidationError(error_msg)
        return new_status

    def validate_is_confirmed_by_customer(self, is_confirmed):
        user = self.context.get('request').user
        if self.instance and user.is_anonymous:
            if self.instance.is_confirmed_by_customer:
                raise ValidationError('Order has been already confirmed.')
            if not Order.can_confirm_with_status(self.instance.status):
                error_msg = 'You\'re not allowed to confirm order with {status} status.'.format(
                    status=self.instance.status
                )
                raise ValidationError(error_msg)
        else:
            raise ValidationError('You\'re not allowed to confirm this order.')
        return is_confirmed

    def validate_capacity(self, capacity):
        user = self.context.get('request').user
        if capacity is not None and not user.current_merchant.enable_job_capacity:
            raise serializers.ValidationError({'capacity': 'Job capacity is not enabled for your merchant.'})
        return capacity


class CommentOrderSerializer(serializers.ModelSerializer):

    customer = BaseCustomerSerializer(read_only=True)

    class Meta:
        model = Order
        fields = ('order_id', 'customer_comment', 'rating', 'updated_at', 'customer', 'id')


class SubBrandingTableSerializer(serializers.ModelSerializer):

    class Meta:
        model = SubBranding
        fields = ('name', 'id')


class OrderTableSerializer(serializers.ModelSerializer):

    assigned_at = serializers.SerializerMethodField()
    driver = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    sub_branding = SubBrandingTableSerializer(read_only=True)
    duration = DurationInSecondsField(read_only=True)

    def __init__(self, *args, **kwargs):
        self.events = kwargs.pop('events', {})
        super(OrderTableSerializer, self).__init__(*args, **kwargs)

    def get_assigned_at(self, instance):
        return self.events.get(instance.id, None)

    def get_driver(self, instance):
        drv = getattr(instance, 'driver')
        return drv.full_name if drv else None

    def get_rating(self, instance):
        if instance.is_confirmed_by_customer:
            return instance.rating or 0
        else:
            return instance.rating

    def get_customer(self, instance):
        cum = getattr(instance, 'customer')
        return cum.name if cum else None

    class Meta:
        model = Order
        fields = ('order_id', 'created_at', 'driver', 'assigned_at', 'rating', 'id',
                  'confirmation_signature', 'duration', 'status', 'updated_at', 'customer_comment',
                  'customer', 'sub_branding')


class BulkDelayedUploadSerializer(DelayedTaskSerializer):
    data = serializers.SerializerMethodField()
    state_params = serializers.SerializerMethodField()
    method = serializers.SerializerMethodField()
    orders_created = serializers.SerializerMethodField()
    original_file_name = serializers.SerializerMethodField()

    class Meta:
        model = BulkDelayedUpload
        fields = DelayedTaskSerializer.Meta.fields + ('orders_created', 'state_params', 'method', 'original_file_name',
                                                      'data',)
        read_only_fields = DelayedTaskSerializer.Meta.read_only_fields + ('orders_created', 'method')

    def get_data(self, instance):
        from .csv import OrderPrototypeErrorSerializer
        return OrderPrototypeErrorSerializer(instance.errors.only('errors', 'line'), many=True).data

    def get_method(self, instance):
        return instance.get_method_display()

    def get_state_params(self, instance):
        instance.update_state()
        return instance.state_params

    def get_orders_created(self, instance):
        instance.update_state()
        return instance.state_params['saved']

    def get_original_file_name(self, instance):
        f = instance.csv_file
        return f.original_file_name if f else f


class OrderLocationWriteMixin(object):
    def validate(self, attrs):
        location = attrs.get('location', None)
        address = attrs.get('address', None)

        # Checking that the location has zero coordinates
        if location and not any(map(float, location.replace(' ', '').split(','))):
            if address is None:
                raise serializers.ValidationError('Location can\'t be "{}"'.format(location))
            location = attrs['location'] = None

        if (location or address) is None:
            raise ValidationError('You should specify either location or address', code='invalid_address')

        if location is None:
            geocoded_from_address = self._process_address_field(address)
            if geocoded_from_address is None:
                raise ValidationError('Address not found.', code='invalid_address')
            attrs.update(geocoded_from_address)

        if address is None:
            attrs['address'] = attrs['location']

        return attrs

    def _process_address_field(self, address):
        user = self.context.get('request').user
        regions = user.current_merchant.countries if hasattr(user, 'current_merchant') else ['AU', ]
        with GoogleClient.track_merchant(user.current_merchant):
            return AddressGeocoder().geocode(address, regions, user.current_merchant.language)


class OrderLocationSerializer(OrderLocationWriteMixin, LocationSerializer, serializers.ModelSerializer):
    location = serializers.CharField(required=False)
    secondary_address = serializers.CharField(max_length=255, required=False, allow_blank=True, write_only=True)

    class Meta:
        model = OrderLocation
        fields = ('id', 'address', 'raw_address', 'location', 'description', 'secondary_address')
        read_only_fields = ('id', )
        validators = []


class OrderLocationSerializerV2(OrderLocationWriteMixin, serializers.ModelSerializer):
    location = LatLngLocation(required=False)
    secondary_address = serializers.CharField(max_length=255, required=False, allow_blank=True, write_only=True)

    class Meta:
        model = OrderLocation
        fields = ('id', 'address', 'raw_address', 'location', 'description', 'secondary_address')
        read_only_fields = ('id',)
        validators = []


class OrderPathSerializer(serializers.ModelSerializer):
    path = serializers.SerializerMethodField()
    path_dict = serializers.DictField(source='path')

    class Meta:
        model = Order
        fields = ('order_id', 'path', 'path_dict')

    def get_path(self, instance):
        if instance.path is None:
            return

        path = OrderedDict((status, instance.path.get(status, []))
                           for status in (instance.PICK_UP, instance.IN_PROGRESS, instance.WAY_BACK))
        return list(chain.from_iterable(path.values())) or instance.path.get('full', [])


class OrderAssignTimeSerializer(serializers.Serializer):
    assign_time = serializers.DateTimeField(read_only=True)


class OrderWaybackTimeSerializer(serializers.Serializer):
    wayback_time = serializers.DateTimeField(read_only=True)


class BaseCustomerAddressSerializer(BaseCustomerSerializer):
    last_address = OrderLocationSerializer(read_only=True)

    class Meta(BaseCustomerSerializer.Meta):
        fields = BaseCustomerSerializer.Meta.fields + ('last_address',)


class OrderPhotoSerializerBase(serializers.ModelSerializer):
    image = Base64ImageField(required=False, allow_null=True)

    class Meta:
        fields = ('image', 'order')
        extra_kwargs = {
            'order': {'write_only': True}
        }


class OrderConfirmationPhotoSerializer(OrderPhotoSerializerBase):
    class Meta(OrderPhotoSerializerBase.Meta):
        model = OrderConfirmationPhoto


class OrderPreConfirmationPhotoSerializer(OrderPhotoSerializerBase):
    class Meta(OrderPhotoSerializerBase.Meta):
        model = OrderPreConfirmationPhoto


class OrderPickUpConfirmationPhotoSerializer(OrderPhotoSerializerBase):
    class Meta(OrderPhotoSerializerBase.Meta):
        model = OrderPickUpConfirmationPhoto
