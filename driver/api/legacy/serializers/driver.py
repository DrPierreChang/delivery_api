from __future__ import absolute_import, unicode_literals

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation as validators
from django.contrib.contenttypes.models import ContentType
from django.core import exceptions
from django.core.validators import MinValueValidator
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property

from rest_framework import serializers
from rest_framework.relations import SlugRelatedField

from constance import config

from base.api.legacy.serializers import UserSerializer
from base.api.legacy.serializers.members import MerchantUserSerializer
from base.models import Car, Member
from base.utils import MobileAppVersionsConstants, get_driver_statistics
from driver.models import DriverLocation
from driver.utils import WorkStatus
from merchant.api.legacy.serializers import HubSerializerV2, MerchantSerializer
from merchant.api.legacy.serializers.hubs import HubLocationSerializerV2
from merchant.api.web.hubs.serializers import HubLocationSerializer
from merchant.models import Hub
from merchant.validators import MerchantsOwnValidator
from radaro_utils.exceptions import TimeMismatchingError
from radaro_utils.radaro_phone.serializers import PhoneField, RadaroPhoneField
from radaro_utils.serializers.fields import UTCTimestampField
from radaro_utils.utils import Pluralizer
from reporting.api.legacy.serializers.serializers import OfflineHappenedAtSerializer
from reporting.context_managers import track_fields_for_offline_changes
from reporting.model_mapping import serializer_map
from reporting.models import Event
from routing.serializers.fields import LatLngLocation
from tasks.api.legacy.serializers.mixins import ActiveOrdersChangesValidationMixin

from .location import DriverLocationSerializer, RetrieveDriverLocationSerializer
from .work_stats import DriverTimeStatisticsSerializer

AuthUserModel = get_user_model()


class DriverManagerSerializer(UserSerializer):
    merchant = serializers.IntegerField(read_only=True, required=False, source='current_merchant_id')

    class Meta(UserSerializer.Meta):
        _force_exclude = {'car', }
        fields = tuple(set(UserSerializer.Meta.fields) - _force_exclude)


class DriverSerializer(UserSerializer):
    manager = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    last_location = DriverLocationSerializer(read_only=True)

    class Meta:
        model = AuthUserModel
        fields = ('id', 'url', 'email', 'password', 'last_location',
                  'first_name', 'last_name', 'car', 'member_id',
                  'avatar', 'is_online', 'work_status', 'phone', 'merchant',
                  'manager', 'status', 'location', 'full_name', 'skill_sets')
        read_only_fields = ('merchant', 'id', 'url', 'manager', 'member_id', 'skill_sets')

    def get_manager(self, obj):
        if obj.current_merchant:
            manager = obj.current_merchant.member_set.filter(Q(role=Member.MANAGER) | Q(role=Member.ADMIN)). \
                select_related('car').order_by('-role').first()
            group_manager = obj.current_merchant.group_managers.filter(role__in=[Member.MANAGER, Member.ADMIN]) \
                .order_by('-role').first()
            manager = manager or group_manager
            return DriverManagerSerializer(instance=manager).data

    def get_location(self, obj):
        return DriverLocationSerializer(obj.last_location).data


class DriverInfoSerializer(DriverSerializer):
    class Meta:
        model = AuthUserModel
        fields = (
            'id', 'member_id', 'first_name', 'last_name',
            'full_name', 'phone', 'avatar', 'thumb_avatar_100x100',
            'skill_sets'
        )


class DriverRegisterSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=256)
    phone = RadaroPhoneField()
    pin_code = serializers.CharField(max_length=10)

    ANDROID = MobileAppVersionsConstants.ANDROID
    APP_TYPES = (
        (ANDROID, 'Android'),
    )
    APP_VARIANTS = [(key, key) for key in settings.ANDROID_SMS_VERIFICATION.keys()]
    app_type = serializers.ChoiceField(required=False, choices=APP_TYPES)
    app_variant = serializers.ChoiceField(required=False, choices=APP_VARIANTS)

    class Meta:
        PAIR_FOUND = 'Phone and pin code pair was found.'
        fields = ('phone', 'password', 'pin_code', 'app_type', 'app_variant')
        required = ('phone', 'password', 'pin_code')

    def __init__(self, query, fields=None, *args, **kwargs):
        # Don't pass the 'fields' arg up to the superclass
        self.query = query
        # Instantiate the superclass normally
        super(DriverRegisterSerializer, self).__init__(*args, **kwargs)

        if fields is not None:
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields.keys())
            for field_name in existing - allowed:
                self.fields.pop(field_name)

    def validate_phone(self, value):
        if Member.objects.filter(phone=value).exists():
            raise serializers.ValidationError('Already registered.')
        else:
            if not self.query.filter(phone=value).exists():
                raise serializers.ValidationError('No invitations with this phone number were found.')
        return value

    def validate_password(self, value):
        try:
            validators.validate_password(value)
        except exceptions.ValidationError as err:
            raise serializers.ValidationError(err.messages)
        return value

    def validate(self, attrs):
        pin = attrs.get('pin_code', None)
        if pin:
            equals_to_master_pin = (pin == config.MASTER_PIN)
            items_by_phone_and_pin = self.query.filter(
                phone=attrs['phone'],
                pin_code=pin,
                pin_code_timestamp__gt=timezone.now() - timedelta(minutes=config.TOKEN_TIMEOUT_MIN)
            )
            if not (items_by_phone_and_pin.exists() or equals_to_master_pin):
                raise serializers.ValidationError('Pin code is not valid or out of date.')

        return attrs

    def get_sms_android_verification_hash(self):
        if self.validated_data.get('app_type', None) == self.ANDROID and 'app_variant' in self.validated_data:
            app_variant = self.validated_data['app_variant']
            return settings.ANDROID_SMS_VERIFICATION[app_variant]


class ListDriverSerializer(UserSerializer):
    merchant = MerchantSerializer(read_only=True, exclude_fields=('has_related_surveys',), source='current_merchant')
    last_location = RetrieveDriverLocationSerializer(read_only=True)
    current_path = serializers.DictField(read_only=True)
    sod_checklist_failed = serializers.SerializerMethodField()
    eod_checklist_failed = serializers.SerializerMethodField()
    has_internet_connection = serializers.BooleanField()
    work_status = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    starting_hub = HubSerializerV2(read_only=True)
    ending_hub = HubSerializerV2(read_only=True)
    ending_point = HubLocationSerializerV2(read_only=True)
    active_orders_count = serializers.IntegerField(required=False)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ('status', 'last_location', 'member_id', 'current_path',
                                               'sod_checklist_failed', 'eod_checklist_failed',
                                               'has_internet_connection', 'skill_sets',
                                               'starting_hub', 'ending_hub', 'ending_point', 'active_orders_count')
        read_only_fields = UserSerializer.Meta.read_only_fields + ('status', 'member_id', 'active_orders_count')

    def get_sod_checklist_failed(self, obj):
        if hasattr(obj, 'sod_checklists') and obj.sod_checklists:
            return obj.sod_checklists[0].is_correct is False
        return False

    def get_eod_checklist_failed(self, obj):
        if hasattr(obj, 'eod_checklists') and obj.eod_checklists:
            return obj.eod_checklists[0].is_correct is False
        return False

    def get_work_status(self, obj):
        return obj.get_work_status_for_manager()

    def get_is_online(self, obj):
        return obj.get_is_online_for_manager()


class UpdateDriverSerializer(serializers.ModelSerializer):
    starting_hub_id = serializers.PrimaryKeyRelatedField(write_only=True, allow_null=True, required=False,
                                                         source='starting_hub', queryset=Hub.objects.all(),
                                                         validators=[MerchantsOwnValidator('hub')])
    ending_hub_id = serializers.PrimaryKeyRelatedField(write_only=True, allow_null=True, required=False,
                                                       source='ending_hub', queryset=Hub.objects.all(),
                                                       validators=[MerchantsOwnValidator('hub')])
    car_capacity = serializers.IntegerField(source='car.capacity', required=False, allow_null=True,
                                            validators=[MinValueValidator(0)])

    ending_point = HubLocationSerializer(required=False, allow_null=True)

    class Meta(ListDriverSerializer.Meta):
        model = get_user_model()
        fields = ('starting_hub_id', 'ending_hub_id', 'ending_point', 'car_capacity')

    def update(self, instance, validated_data):
        car_data = validated_data.pop('car', {})
        if car_data:
            instance.car, _ = Car.objects.update_or_create(member__id=instance.id, defaults=car_data)

        if 'ending_point' in validated_data:
            validated_data['ending_point'] = self.fields['ending_point'].create(validated_data['ending_point'])

        return super().update(instance, validated_data)


@serializer_map.register_serializer_for_detailed_dump(version=1)
class DumpListDriverSerializer(ListDriverSerializer):
    phone = PhoneField()


class ListDriverSerializerV2(ListDriverSerializer):
    class Meta(ListDriverSerializer.Meta):
        fields = ListDriverSerializer.Meta.fields + ('id',)


@serializer_map.register_serializer_for_detailed_dump(version='web')
@serializer_map.register_serializer_for_detailed_dump(version=2)
class DumpListDriverSerializerV2(ListDriverSerializerV2):
    phone = PhoneField()


class MerchantsDriverSerializer(DriverSerializer):
    manager = serializers.SerializerMethodField()
    merchant = serializers.IntegerField(read_only=True, source='current_merchant_id')
    location = serializers.SerializerMethodField()
    work_status_stats = serializers.SerializerMethodField()

    class Meta:
        model = AuthUserModel
        fields = ('email', 'password', 'member_id',
                  'first_name', 'last_name', 'car',
                  'avatar', 'is_online', 'work_status', 'phone',
                  'thumb_avatar_100x100', 'full_name',
                  'status', 'location', 'manager', 'merchant',
                  'work_status_stats')

    def get_manager(self, obj):
        if obj.current_merchant:
            manager = obj.current_merchant.member_set.filter(Q(role=Member.MANAGER) | Q(role=Member.ADMIN)). \
                order_by('-role').first()
            group_manager = obj.current_merchant.group_managers.filter(role__in=[Member.MANAGER, Member.ADMIN]) \
                .order_by('-role').first()
            manager = manager or group_manager
            return MerchantDriverManagerSerializer(instance=manager, context=self.context).data
        return

    def get_location(self, obj):
        last_location = obj.last_location
        if last_location:
            return last_location.improved_location or last_location.location
        return

    def get_work_status_stats(self, obj):
        driver_stats = get_driver_statistics(obj)
        return {
            'time_stats': DriverTimeStatisticsSerializer(driver_stats).data,
            'history': driver_stats['past_seven_days']['history'],
        }


class MerchantDriverManagerSerializer(MerchantUserSerializer):
    merchant = serializers.IntegerField(read_only=True, required=False, source='current_merchant_id')


class DriversDestroyValidationMixin(ActiveOrdersChangesValidationMixin):

    def _get_active_error_msg(self, jobs_ids, relations):
        msg = 'Can\'t delete the {1:driver/s} because {1:he/they} {1:has/have} "{0:N}" ' \
              'active {0:job/s} that {1:ha/s/ve} the skill.'
        return msg.format(Pluralizer(len(jobs_ids)), Pluralizer(len(relations)))

    def _get_assigned_error_msg(self, jobs_ids, relations):
        msg = '"{0:N}" {0:job/s} that {0:ha/s/ve} the skill will be unassigned ' \
              'from {1:driver/s} after you delete the skill.'
        return msg.format(Pluralizer(len(jobs_ids)), Pluralizer(len(relations)))


class RelativeDriverSerializer(DriversDestroyValidationMixin, serializers.Serializer):
    drivers = serializers.ManyRelatedField(
        required=False,
        child_relation=SlugRelatedField(
            queryset=Member.drivers.all(),
            slug_field='member_id',
            required=False
        )
    )

    def validate(self, attrs):
        request = self.context.get('request')
        skill_set = self.context.get('skill_set')
        drivers = attrs.get('drivers', [])

        if request.method == 'DELETE':
            self._validate_on_destroy(
                drivers,
                skill_set.orders.all().annotate_job_type_for_drivers(drivers)
            )
        return attrs


class LocationSerializer(serializers.ModelSerializer):
    location = LatLngLocation()

    class Meta:
        model = DriverLocation
        fields = ('location',)


class DriverStatusSerializer(OfflineHappenedAtSerializer, serializers.Serializer):
    is_online = serializers.BooleanField(required=False)
    work_status = serializers.ChoiceField(required=False, choices=Member.work_status_choices)
    location = LocationSerializer(write_only=True, required=False)
    offline_happened_at = UTCTimestampField(write_only=True, required=False)

    @cached_property
    def last_happened_at(self):
        driver_ct = ContentType.objects.get_for_model(Member)
        driver = self.instance or self.parent.instance
        events = Event.objects.filter(
            object_id=driver.id, content_type=driver_ct, event=Event.CHANGED, field='work_status')
        last_event = events.order_by('-happened_at').first()
        return last_event.happened_at if last_event else None

    def validate_offline_happened_at(self, attr):
        if self.last_happened_at and attr < self.last_happened_at:
            raise TimeMismatchingError(
                reason='The new event must be later than the last event', last_item_time=self.last_happened_at)
        return attr

    def validate(self, attrs):
        if 'work_status' not in attrs:
            if 'is_online' not in attrs:
                serializers.ValidationError('Must be the field "is_online", or "work_status".')
            else:
                attrs['work_status'] = WorkStatus.WORKING if attrs['is_online'] else WorkStatus.NOT_WORKING

        return attrs

    def _update(self, instance, validated_data):
        instance.set_availability_status(validated_data['work_status'], self.context['request'].user)
        return instance

    @staticmethod
    def get_location_data_for_work_status(location):
        if not location:
            return None
        return {
            'last_location': {
                'location': location,
            }
        }

    def _get_data_for_event(self, instance, validated_data):
        location = None
        if 'location' in validated_data:
            location = validated_data['location']['location']
        if not location and 'offline_happened_at' not in validated_data and instance.last_location:
            location = instance.last_location.location
        if not location:
            return None

        return {
            'additional_info_for_fields': {
                'work_status': self.get_location_data_for_work_status(location)
            }
        }

    def update(self, instance, validated_data):
        offline_happened_at = validated_data.get('offline_happened_at', None)
        request = self.context['request']
        with track_fields_for_offline_changes(instance, self, request, offline_happened_at) as event_fields:
            event_fields['instance'] = self._update(instance, validated_data)
            event_fields['additional_data_for_event'] = self._get_data_for_event(instance, validated_data)
        return instance

    @property
    def data(self):
        data = super().data
        if not self.context['request'].user.is_driver:
            data['work_status'] = self.instance.get_work_status_for_manager()
            data['is_online'] = self.instance.get_is_online_for_manager()
        return data


class DriverStatusListSerializer(serializers.ListSerializer):
    child = DriverStatusSerializer()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.child.fields['offline_happened_at'].required = True

    def update(self, instance, validated_data):
        validated_data = sorted(validated_data, key=lambda item: item['offline_happened_at'])

        for item in validated_data:
            instance = self.child.update(instance, item)
        return instance
