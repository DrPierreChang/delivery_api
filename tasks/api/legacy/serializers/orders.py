import collections
from itertools import chain

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import SerializerMethodField

from base.api.legacy.serializers.fields import MarkdownField
from base.models import Member
from driver.api.legacy.serializers.driver import DriverSerializer
from merchant.api.legacy.serializers import (
    HubSerializer,
    HubSerializerV2,
    LabelHexSerializer,
    LabelSerializer,
    SubBrandingSerializer,
)
from merchant.api.legacy.serializers.merchants import CustomerGetBrandSerializer
from merchant.api.legacy.serializers.skill_sets import OrderSkillSetsValidationMixin
from merchant.models import Hub
from merchant.validators import MerchantsOwnValidator
from merchant_extension.api.legacy.serializers import RetrieveResultChecklistSerializer
from merchant_extension.api.legacy.serializers.survey import SurveyResultSerializer
from radaro_utils.helpers import validate_photos_count
from radaro_utils.serializers.fields import Base64ImageField, ParseDateTimeField, UTCTimestampField
from radaro_utils.serializers.validators import LaterThenNowValidator, ValidateLaterDoesNotExist
from reporting.api.legacy.serializers.delta import DeltaSerializer
from reporting.model_mapping import serializer_map
from reporting.models import Event
from routing.serializers.fields import LatLngLocation
from tasks.mixins.order_status import OrderStatus
from tasks.models import (
    Order,
    OrderConfirmationPhoto,
    OrderLocation,
    OrderPickUpConfirmationPhoto,
    OrderPreConfirmationPhoto,
)
from tasks.models.terminate_code import TerminateCode

from .barcode import BarcodeListSerializer
from .cargoes import DeltaOrderCargoes, DriverOrderCargoes, OrderCargoesMixin
from .core import (
    BaseOrderSerializer,
    OrderConfirmationPhotoSerializer,
    OrderLocationSerializer,
    OrderLocationSerializerV2,
    OrderPreConfirmationPhotoSerializer,
)
from .customers import CustomerSerializer, PickupSerializer
from .documents import OrderConfirmationDocumentSerializer
from .mixins import (
    BarcodesUnpackMixin,
    CustomerUnpackMixin,
    OfflineHappenedAtMixin,
    OrderLocationUnpackMixin,
    PickupUnpackMixin,
    UnpackOrderPhotosMixin,
    ValidateConfirmationMixin,
    ValidateJobIntervalsMixin,
)
from .terminate_code import TerminateCodeNumberSerializer

METERS_IN_MILE = 1609.34


class OrderSerializer(ValidateJobIntervalsMixin,
                      OrderSkillSetsValidationMixin,
                      BarcodesUnpackMixin,
                      CustomerUnpackMixin,
                      OrderLocationUnpackMixin,
                      PickupUnpackMixin,
                      OrderCargoesMixin,
                      BaseOrderSerializer):
    location_class = OrderLocation
    location_names = ('pickup_address', 'deliver_address', 'starting_point', 'ending_point')

    customer = CustomerSerializer()
    deliver_address = OrderLocationSerializer()
    pickup_address = OrderLocationSerializer(required=False, allow_null=True)
    starting_point = OrderLocationSerializer(required=False)
    wayback_point = OrderLocationSerializer(required=False, read_only=True)
    wayback_hub = HubSerializer(required=False, read_only=True)
    ending_point = OrderLocationSerializer(required=False)
    order_confirmation_photos = OrderConfirmationPhotoSerializer(many=True, read_only=True)
    confirmation_signature = Base64ImageField(read_only=True)
    description = MarkdownField(allow_blank=True, allow_null=True, required=False)
    pre_confirmation_photos = OrderPreConfirmationPhotoSerializer(many=True, read_only=True)
    pre_confirmation_signature = Base64ImageField(read_only=True)
    order_confirmation_documents = OrderConfirmationDocumentSerializer(many=True, read_only=True)
    pickup = PickupSerializer(required=False, allow_null=True)
    pickup_after = ParseDateTimeField(required=False, allow_null=True)
    pickup_before = ParseDateTimeField(required=False, allow_null=True, validators=[LaterThenNowValidator()])
    pick_up_confirmation_photos = OrderConfirmationPhotoSerializer(many=True, read_only=True)
    pick_up_confirmation_signature = Base64ImageField(read_only=True)
    public_report_link = serializers.CharField(read_only=True)
    statuses_time_distance = serializers.DictField(read_only=True)
    picked_up_at = serializers.DateTimeField(read_only=True)
    in_progress_at = serializers.DateTimeField(read_only=True)
    assigned_at = serializers.DateTimeField(read_only=True)
    wayback_at = serializers.DateTimeField(read_only=True)

    class Meta(BaseOrderSerializer.Meta):
        read_only_fields = BaseOrderSerializer.Meta.read_only_fields + \
                           ('rating', 'customer_comment', 'confirmation_comment',
                            'order_confirmation_photos', 'pre_confirmation_photos',
                            'pre_confirmation_signature', 'pre_confirmation_comment',
                            'pick_up_confirmation_photos', 'pick_up_confirmation_signature',
                            'pick_up_confirmation_comment')

    @staticmethod
    def _validate_terminate_code(terminate_code, terminate_comment, corresponding_status, code_type):
        if not corresponding_status and (terminate_code or terminate_comment):
            raise ValidationError('You can not pass {0} code with this status.'.format(code_type))
        if [code for code in terminate_code if code.is_comment_necessary] and not terminate_comment:
            raise ValidationError('{0} comment is required.'.format(code_type.title()))

    def _check_is_merchants_attr(self, attr, attr_name, merchant):
        if attr:
            attr_merchant = attr.current_merchant if isinstance(attr, Member) else attr.merchant
            if merchant != attr_merchant:
                raise ValidationError("This is not merchant's {}".format(attr_name))

    def validate(self, attrs):
        super().validate(attrs)
        validate_merchant_attrs_names = ['driver', 'labels', 'sub_branding', 'skill_sets']
        no_value = object()

        merchant = self._get_order_merchant(attrs)
        self._validate_job_intervals(attrs, merchant)

        pickup, pickup_address = attrs.get('pickup'), \
                                 attrs.get('pickup_address', self.instance.pickup_address if self.instance else None)
        if pickup and not pickup_address:
            raise serializers.ValidationError({'pickup': 'You can\'t add pickup to order without pickup address.'})

        terminate_comment = attrs.get('terminate_comment')

        terminate_code = attrs.pop('terminate_code', no_value)
        if attrs.get('terminate_codes'):
            terminate_code = attrs.get('terminate_codes')

        if terminate_code is not no_value:
            if terminate_code:
                if not isinstance(terminate_code, collections.Iterable):
                    terminate_code = [terminate_code, ]
            else:
                terminate_code = []

            attrs['terminate_codes'] = terminate_code
        else:
            terminate_code = None

        code_type = terminate_code[0].type if terminate_code else None

        if code_type == TerminateCode.TYPE_ERROR:
            status_is_failed = attrs.get('status') == OrderStatus.FAILED
            self._validate_terminate_code(terminate_code, terminate_comment, status_is_failed, code_type)
        elif code_type == TerminateCode.TYPE_SUCCESS:
            status_is_finished = OrderStatus.can_confirm_with_status(
                attrs.get('status', self.instance.status if self.instance else None))
            self._validate_terminate_code(terminate_code, terminate_comment, status_is_finished, code_type)
            if not merchant.advanced_completion_enabled and (terminate_code or terminate_comment):
                raise ValidationError('Success codes are disabled for your merchant.')

        label = attrs.pop('label', no_value)
        if label not in [None, no_value]:
            attrs['labels'] = [label, ]
        elif label is None:
            attrs['labels'] = []

        validate_merchant_attrs = [x for x in attrs if x in validate_merchant_attrs_names]
        if validate_merchant_attrs:
            for name in validate_merchant_attrs:
                attr = attrs.get(name, None)
                if not isinstance(attr, list):
                    self._check_is_merchants_attr(attr, name, merchant)
                else:
                    [self._check_is_merchants_attr(single_attr, name, merchant) for single_attr in attr]

        driver = attrs.get('driver', self.instance.driver if self.instance else None)
        skill_sets = attrs.get('skill_sets', self.instance.skill_sets.all() if self.instance else None)

        self._validate_skill_sets_for_driver(
            skill_sets=skill_sets,
            driver=driver
        )

        return attrs

    def _get_order_merchant(self, attrs):
        merchant = self.context['request'].user.current_merchant
        return merchant

    def validate_description(self, attr):
        request = self.context['request']
        if not request.user.current_merchant.enable_job_description:
            raise ValidationError("Rich text job descriptions disabled.")
        return attr


class OrderSerializerV2(OrderSerializer):
    customer = CustomerSerializer()

    deliver_address = OrderLocationSerializerV2()
    pickup_address = OrderLocationSerializerV2(required=False, allow_null=True)
    starting_point = OrderLocationSerializerV2(required=False)
    ending_point = OrderLocationSerializerV2(required=False)
    wayback_point = OrderLocationSerializerV2(required=False, read_only=True)
    wayback_hub = HubSerializerV2(required=False, read_only=True)

    manager = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta(OrderSerializer.Meta):
        _force_include = {'id', }
        _read_only = ('id', 'label', )
        exclude = tuple(set(OrderSerializer.Meta.exclude) - _force_include)
        read_only_fields = OrderSerializer.Meta.read_only_fields + _read_only


@serializer_map.register_serializer
class OrderDeltaSerializer(DeltaSerializer):
    terminate_code = TerminateCodeNumberSerializer(required=False)
    completion_codes = TerminateCodeNumberSerializer(required=False, many=True, source='terminate_codes')
    completion_comment = serializers.CharField(required=False, source='terminate_comment')
    barcodes = BarcodeListSerializer(required=False)
    cargoes = DeltaOrderCargoes(source='*', required=False)

    class Meta(DeltaSerializer.Meta):
        model = Order
        track_change_event = ('status', 'pickup_geofence_entered', 'geofence_entered', 'geofence_entered_on_backend',
                              'rating',)


@serializer_map.register_serializer_for_detailed_dump(version=1)
class RetrieveOrderSerializer(OrderSerializer):
    exclude_driver_fields = ('email', 'merchant', 'manager')
    driver = DriverSerializer(exclude_fields=exclude_driver_fields, read_only=True)
    sub_branding = SubBrandingSerializer(required=False)
    label = LabelSerializer(required=False)
    labels = LabelSerializer(required=False, many=True)


@serializer_map.register_serializer_for_detailed_dump(version=2)
class RetrieveOrderSerializerV2(OrderSerializerV2):
    real_path = serializers.SerializerMethodField()
    real_path_dict = serializers.DictField(source='real_path')
    in_progress_point = serializers.SerializerMethodField()

    def get_real_path(self, instance):
        if instance.real_path is None:
            return

        real_path = collections.OrderedDict((status, instance.real_path.get(status, []))
                                            for status in (instance.PICK_UP, instance.IN_PROGRESS, instance.WAY_BACK))
        return list(chain.from_iterable(real_path.values())) or instance.real_path.get('full', [])

    def get_in_progress_point(self, instance):
        return {'location': LatLngLocation().to_representation(instance.in_progress_point)} \
            if instance.in_progress_point else None


class ListOrderSerializerV2(BaseOrderSerializer):
    customer = CustomerSerializer()
    pickup = PickupSerializer()

    description = MarkdownField(allow_blank=True, allow_null=True, required=False)

    starting_point = OrderLocationSerializerV2(required=False)
    label = None

    manager = serializers.PrimaryKeyRelatedField(queryset=Member.managers.all())
    driver = serializers.PrimaryKeyRelatedField(queryset=Member.drivers.all())

    deliver_address = OrderLocationSerializerV2()
    pickup_address = OrderLocationSerializerV2(required=False, allow_null=True)

    assigned_at = serializers.DateTimeField(read_only=True)
    wayback_at = serializers.DateTimeField(read_only=True)
    wayback_point = OrderLocationSerializerV2(required=False, read_only=True)
    wayback_hub = HubSerializerV2(required=False, read_only=True)

    class Meta(BaseOrderSerializer.Meta):
        _force_include = {'id', }
        _hide_from_list = {'ending_point', 'real_path', 'confirmation_signature'}
        _exclude = set(BaseOrderSerializer.Meta.exclude).union(_hide_from_list) - _force_include
        exclude = tuple(_exclude)


class OrderDeadlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ('deliver_before', 'id')


class OrderIDSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ('id',)


class DriverCreateOrderSerializerFieldsMixin(object):

    class Meta:
        model = Order
        fields = ('customer', 'deliver_address', 'deliver_address_2', 'pickup_address', 'pickup_address_2',
                  'pickup', 'pickup_after', 'pickup_before', 'deliver_after', 'deliver_before', 'title',
                  'comment', 'status', 'driver', 'order_id', 'sort_rate', 'label', 'labels', 'sub_branding',
                  'skill_sets', 'barcodes', 'capacity')
        read_only_fields = ('order_id', 'sort_rate')


class DriverCreateOrderSerializer(DriverCreateOrderSerializerFieldsMixin, OrderSerializer):
    pass


class DriverCreateOrderSerializerV2(DriverCreateOrderSerializerFieldsMixin, OrderSerializerV2):
    server_entity_id = serializers.IntegerField(source='id', required=False)

    class Meta(DriverCreateOrderSerializerFieldsMixin.Meta):
        _exclude = {'label'}
        fields = tuple((set(DriverCreateOrderSerializerFieldsMixin.Meta.fields) | {'server_entity_id'}) - _exclude)
        read_only_fields = DriverCreateOrderSerializerFieldsMixin.Meta.read_only_fields + ('server_entity_id', )


class DriverOrderSerializer(OfflineHappenedAtMixin, UnpackOrderPhotosMixin, ValidateConfirmationMixin, OrderSerializer):
    order_confirmation_photos = OrderConfirmationPhotoSerializer(required=False, many=True, allow_null=True)
    confirmation_signature = Base64ImageField(required=False, allow_null=True)
    pre_confirmation_photos = OrderPreConfirmationPhotoSerializer(required=False, many=True, allow_null=True)
    pre_confirmation_signature = Base64ImageField(required=False, allow_null=True)
    pick_up_confirmation_photos = OrderConfirmationPhotoSerializer(required=False, many=True, allow_null=True)
    pick_up_confirmation_signature = Base64ImageField(required=False, allow_null=True)
    distance = SerializerMethodField(required=False, allow_null=True, read_only=True)
    duration = serializers.DurationField(read_only=True)
    order_is_confirmed = SerializerMethodField()
    is_pre_confirmed = SerializerMethodField()
    is_pick_up_confirmed = SerializerMethodField()
    driver_checklist = RetrieveResultChecklistSerializer(read_only=True, required=False)
    is_archived = SerializerMethodField()
    offline_happened_at = UTCTimestampField(required=False, allow_null=True)
    label = LabelSerializer(required=False, read_only=True)
    labels = LabelSerializer(required=False, many=True, read_only=True)
    cargoes = DriverOrderCargoes(source='*', required=False)

    confirmation_photos_list = [('order_confirmation_photos', OrderConfirmationPhoto),
                                ('pre_confirmation_photos', OrderPreConfirmationPhoto),
                                ('pick_up_confirmation_photos', OrderPickUpConfirmationPhoto)]

    class Meta(OrderSerializer.Meta):
        exclude = OrderSerializer.Meta.exclude + ('driver', 'real_path')
        read_only_fields = BaseOrderSerializer.Meta.read_only_fields + \
                           ('title', 'comment', 'deliver_after', 'deliver_before',
                            'pickup_after', 'pickup_before', 'pickup_address',
                            'pickup_address_2', 'pickup', 'deliver_address',
                            'deliver_address_2', 'manager', 'order_is_confirmed',
                            'customer', 'rating', 'customer_comment')

    lookups_for_geofence = {
        True: dict(field='status', new_value__in=[OrderStatus.IN_PROGRESS, OrderStatus.PICK_UP, OrderStatus.ASSIGNED]),
        False: dict(field='geofence_entered', new_value=True)
    }
    lookups_for_pickup_geofence = {
        True: dict(field='status', new_value__in=[OrderStatus.ASSIGNED]),
        False: dict(field='pickup_geofence_entered', new_value=True)
    }
    lookups_for_statuses = {
        OrderStatus.IN_PROGRESS: dict(field='status', new_value__in=[OrderStatus.ASSIGNED, OrderStatus.PICK_UP]),
        OrderStatus.PICK_UP: dict(field='status', new_value=OrderStatus.ASSIGNED),
        OrderStatus.NOT_ASSIGNED: dict(field='status', new_value=OrderStatus.ASSIGNED),
        OrderStatus.DELIVERED: dict(
            field='status', new_value__in=[OrderStatus.IN_PROGRESS, OrderStatus.PICK_UP, OrderStatus.ASSIGNED]
        ),
    }

    def validate(self, attrs):
        super(DriverOrderSerializer, self).validate(attrs)
        status = attrs.get('status')
        order_starts = status == OrderStatus.PICK_UP \
            or (status == OrderStatus.IN_PROGRESS and self.instance.status != OrderStatus.PICK_UP)
        if not order_starts and attrs.get('starting_point'):
            if status != OrderStatus.IN_PROGRESS:
                raise ValidationError("Starting point is not allowed.")
            attrs.pop('starting_point')
        if status not in [OrderStatus.DELIVERED, OrderStatus.FAILED] and attrs.get('ending_point'):
            raise ValidationError("Ending point is not allowed.")

        offline_happened_at = attrs.pop('offline_happened_at', None)
        pickup_geofence_entered, geofence_entered = attrs.get('pickup_geofence_entered'), attrs.get('geofence_entered')
        if offline_happened_at:
            events = self.instance.events.all().filter(event=Event.CHANGED)
            attrs['changed_in_offline'] = True
            if order_starts and not attrs.get('starting_point'):
                raise serializers.ValidationError("Field 'starting_point' was not passed.")

            if pickup_geofence_entered is not None:
                ValidateLaterDoesNotExist(events.filter(**self.lookups_for_pickup_geofence[pickup_geofence_entered]),
                                          'happened_at')(offline_happened_at)
            if geofence_entered is not None:
                ValidateLaterDoesNotExist(events.filter(**self.lookups_for_geofence[geofence_entered]),
                                          'happened_at')(offline_happened_at)
            if status in self.lookups_for_statuses:
                ValidateLaterDoesNotExist(events.filter(**self.lookups_for_statuses[status]),
                                          'happened_at')(offline_happened_at)

        if self.instance.allow_order_completion_in_geofence(geofence_entered, check_order_status=True):
            attrs['status'] = Order.DELIVERED if not self.instance.merchant.use_way_back_status else Order.WAY_BACK
            attrs['is_completed_by_geofence'] = True

        return attrs

    def get_distance(self, inst):
        if hasattr(inst, 'distance') and inst.distance is not None:
            return float(inst.distance) * METERS_IN_MILE

    # Confirmed by driver
    def get_order_is_confirmed(self, instance):
        return any([instance.confirmation_signature, instance.order_confirmation_photos.exists()])

    def get_is_pre_confirmed(self, instance):
        return any([instance.pre_confirmation_signature, instance.pre_confirmation_photos.exists()])

    def get_is_pick_up_confirmed(self, instance):
        return any([instance.pick_up_confirmation_signature,
                    instance.pick_up_confirmation_photos.exists(),
                    instance.pick_up_confirmation_comment])

    def get_is_archived(self, instance):
        if hasattr(instance, 'archived'):
            return instance.archived
        return False

    def validate_geofence_entered(self, attr):
        self._validate_geofence_entered(field='geofence_entered', value=attr)
        return attr

    def validate_pickup_geofence_entered(self, attr):
        self._validate_geofence_entered(field='pickup_geofence_entered', value=attr)
        return attr

    def _validate_geofence_entered(self, field, value):
        if getattr(self.instance, field) is None and not value:
            raise ValidationError("Can not mark {} as False before entering.".format(field))
        elif getattr(self.instance, field) and value:
            raise ValidationError("{} has been already marked as True.".format(field))
        elif getattr(self.instance, field) is False:
            raise ValidationError("{} has been already marked as False.".format(field))

    def validate_order_confirmation_photos(self, attr):
        if attr is not None:
            return validate_photos_count(attr)

    def validate_pre_confirmation_photos(self, attr):
        if attr is not None:
            return validate_photos_count(attr)

    def validate_pick_up_confirmation_photos(self, attr):
        if attr is not None:
            return validate_photos_count(attr)

    def get_driver_checklist_passed(self, instance):
        if instance.driver_checklist:
            return instance.driver_checklist.is_passed
        return False

    def get_driver_checklist_confirmed(self, instance):
        if instance.driver_checklist:
            return instance.driver_checklist.is_confirmed
        return False


class DriverOrderSerializerV2(DriverOrderSerializer):
    server_entity_id = serializers.IntegerField(source='id')
    labels = LabelHexSerializer(required=False, many=True, read_only=True)
    label = None
    wayback_hub = HubSerializerV2(required=False, read_only=True)
    external_id = serializers.SerializerMethodField()
    ro_details = serializers.SerializerMethodField()

    class Meta(DriverOrderSerializer.Meta):
        read_only_fields = DriverOrderSerializer.Meta.read_only_fields + ('external_id', 'ro_details',)

    def get_external_id(self, instance):
        return instance.external_job.external_id if instance.external_job else None

    def get_ro_details(self, instance):
        ro_details = instance.route_optimisation_details
        if not ro_details:
            return None
        result_details = {}
        delivery_details = ro_details['delivery'] or {}
        result_details['planned_arrival_after'] = delivery_details.get('planned_arrival_after', None)
        result_details['planned_arrival_before'] = delivery_details.get('planned_arrival_before', None)
        result_details['planned_arrival'] = delivery_details.get('planned_arrival', None)
        pickup_details = ro_details['pickup'] or {}
        result_details['pickup_planned_arrival_after'] = pickup_details.get('planned_arrival_after', None)
        result_details['pickup_planned_arrival_before'] = pickup_details.get('planned_arrival_before', None)
        result_details['pickup_planned_arrival'] = pickup_details.get('planned_arrival', None)
        return {key: serializers.DateTimeField().to_representation(value) for key, value in result_details.items()}


class CustomerSurveySerializer(SurveyResultSerializer):
    brand = SerializerMethodField()

    class Meta(SurveyResultSerializer.Meta):
        fields = SurveyResultSerializer.Meta.fields + ('brand', )

    def get_brand(self, instance):
        order = instance.customer_order
        brand_info = order.sub_branding or order.merchant
        obj = getattr(order, order.merchant.customer_tracking_phone_settings, None)
        phone = obj.phone if obj else ''
        return CustomerGetBrandSerializer(brand_info, context={'phone': phone}).data


class OrderCurrentLocationSerializer(OrderSerializer):
    current_location = OrderLocationSerializer()
    driver_status = SerializerMethodField()
    location_names = ('current_location',)

    class Meta:
        model = Order
        fields = ('pickup_address', 'pickup_address_2', 'starting_point', 'deliver_address', 'deliver_address_2',
                  'current_location', 'driver_status')

    def get_driver_status(self, instance):
        return instance.driver.status


class GeofenceEnteredRequestSerializer(serializers.Serializer):
    geofence_entered = serializers.BooleanField(required=True)
    offline_happened_at = serializers.FloatField(required=False, allow_null=True)

    def __init__(self, order_status, *args, **kwargs):
        self.order_status = order_status
        super().__init__(*args, **kwargs)

    def validate(self, attrs):
        geofence_entered = attrs.pop('geofence_entered')
        if self.order_status == OrderStatus.PICK_UP:
            attrs['pickup_geofence_entered'] = geofence_entered
        elif self.order_status == OrderStatus.IN_PROGRESS:
            attrs['geofence_entered'] = geofence_entered
        else:
            raise serializers.ValidationError("You can send geofence data only when order is in 'pickup' or"
                                              "'in_progress' status.")
        return attrs


class WaybackPointSerializer(OfflineHappenedAtMixin, OrderLocationUnpackMixin, serializers.ModelSerializer):
    location_class = OrderLocation
    location_names = ('wayback_point', )

    wayback_point = OrderLocationSerializerV2(allow_null=True, required=False)
    wayback_hub = serializers.PrimaryKeyRelatedField(queryset=Hub.objects.all(), required=False, allow_null=True,
                                                     validators=[MerchantsOwnValidator('hub')])
    offline_happened_at = UTCTimestampField(required=False, allow_null=True)

    class Meta:
        model = Order
        fields = ('wayback_point', 'wayback_hub', 'offline_happened_at')

    def validate(self, attrs):
        attrs = super(WaybackPointSerializer, self).validate(attrs)
        if self.instance.status != OrderStatus.WAY_BACK:
            raise serializers.ValidationError("Can't set wayback_point")
        if attrs.get('wayback_point') and attrs.get('wayback_hub'):
            raise serializers.ValidationError("Can't set both 'wayback_point' and 'wayback_hub'")
        if attrs.get('wayback_point'):
            attrs['wayback_hub'] = None
        if attrs.get('wayback_hub'):
            attrs['wayback_point'] = None

        offline_happened_at = attrs.pop('offline_happened_at', None)
        if offline_happened_at:
            attrs['changed_in_offline'] = True
            events = self.instance.events.all().filter(event=Event.CHANGED, field='status',
                                                       new_value=OrderStatus.WAY_BACK)
            ValidateLaterDoesNotExist(events, 'happened_at')(offline_happened_at)

        return attrs


class BarcodeInformationSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer()
    deliver_address = OrderLocationSerializer()
    pickup_address = OrderLocationSerializer()
    barcodes = BarcodeListSerializer()

    class Meta:
        model = Order
        fields = ('id', 'title', 'customer', 'status', 'deliver_address', 'pickup_address', 'barcodes')
