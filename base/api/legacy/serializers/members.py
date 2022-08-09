from __future__ import unicode_literals

from django.contrib.auth import get_user_model

from rest_framework import serializers

from merchant.api.legacy.serializers import MerchantSerializer, SubBrandingSerializer
from merchant.models import Merchant
from radaro_router.exceptions import RadaroRouterClientException
from radaro_utils.radaro_phone.serializers import PhoneField, RadaroPhoneField
from radaro_utils.serializers.fields import Base64ImageField
from radaro_utils.serializers.mixins import SerializerExcludeFieldsMixin
from reporting.api.legacy.serializers.delta import DeltaSerializer
from reporting.model_mapping import serializer_map

from .cars import CarSerializer
from .mixins import CarUnpackMixin, SetPasswordMixin


class UserSerializer(SerializerExcludeFieldsMixin, CarUnpackMixin, SetPasswordMixin, serializers.ModelSerializer):
    car_field_names = ['car']

    merchant = MerchantSerializer(read_only=True, source='current_merchant')
    avatar = Base64ImageField(allow_null=True)
    car = CarSerializer()
    phone = RadaroPhoneField()
    can_make_payment = serializers.SerializerMethodField(method_name='make_payment')
    role = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ('id', 'email', 'password',
                  'first_name', 'last_name', 'car',
                  'avatar', 'is_online', 'work_status', 'phone',
                  'merchant', 'thumb_avatar_100x100',
                  'can_make_payment', 'merchant_position',
                  'full_name', 'role', 'deleted')
        read_only_fields = ('merchant', 'id', 'is_online', 'work_status', 'car',
                            'thumb_avatar_100x100', 'can_make_payment',
                            'merchant_position', 'deleted')

    def make_payment(self, obj):
        if obj.is_admin:
            return True
        return False

    def get_role(self, instance):
        return instance.get_role_display()

    def validate(self, attrs):
        if 'email' not in attrs or not self.instance:
            return attrs

        params = {
            'username': self.instance.username,
            'email': attrs['email'],
            'remote_id': self.instance.radaro_router.remote_id
        }

        try:
            self.instance.check_instance(params)
        except RadaroRouterClientException as exc:
            errors = exc.errors.get('errors', '')
            raise serializers.ValidationError(errors)

        return attrs


class MerchantUserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        fields = ('member_id', 'email', 'password',
                  'first_name', 'last_name', 'car',
                  'avatar', 'is_online', 'work_status', 'phone',
                  'merchant', 'thumb_avatar_100x100',
                  'can_make_payment', 'merchant_position',
                  'full_name', 'role')
        read_only_fields = ('merchant', 'member_id', 'is_online', 'work_status', 'car',
                            'thumb_avatar_100x100', 'can_make_payment',
                            'merchant_position')


class SmallUserInfoSerializer(serializers.ModelSerializer):
    car = CarSerializer()
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, inst):
        last_name = ' ' + inst.last_name if inst.last_name else ''
        return u'' + inst.first_name + last_name

    class Meta:
        model = get_user_model()
        fields = ('id', 'full_name', 'car',
                  'is_online', 'work_status', 'phone', 'thumb_avatar_100x100',
                  'merchant_position')
        read_only_fields = ('id', 'full_name', 'car',
                            'is_online', 'work_status', 'phone', 'thumb_avatar_100x100',
                            'merchant_position')


class UserDumpSerializer(serializers.ModelSerializer):
    car = CarSerializer()
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, inst):
        last_name = ' ' + inst.last_name if inst.last_name else ''
        return u'' + inst.first_name + last_name

    class Meta:
        model = get_user_model()
        fields = ('id', 'email', 'password', 'full_name',
                  'first_name', 'last_name', 'car', 'merchant',
                  'avatar', 'is_online', 'work_status', 'phone', 'merchant_position')
        read_only_fields = ('id', 'email', 'password', 'first_name', 'last_name',
                            'car', 'avatar', 'is_online', 'work_status', 'phone', 'merchant',
                            'merchant_position')


@serializer_map.register_serializer
class UserDeltaSerializer(DeltaSerializer):
    phone = PhoneField()
    is_online = serializers.BooleanField()
    car = CarSerializer()

    class Meta(DeltaSerializer.Meta):
        model = get_user_model()
        fields = None
        exclude = ('merchant', 'password')
        track_change_event = ('work_status', 'is_online', 'is_active', 'is_offline_forced')


class HubDriverSerializer(MerchantUserSerializer):
    car = CarSerializer()


class ManagerSerializer(UserSerializer):
    enable_labels = serializers.BooleanField(source='current_merchant.enable_labels')
    use_pick_up_status = serializers.BooleanField(source='current_merchant.use_pick_up_status')
    use_way_back_status = serializers.BooleanField(source='current_merchant.use_way_back_status')
    merchant_id = serializers.PrimaryKeyRelatedField(write_only=True, queryset=Merchant.objects.all(), required=False,
                                                     source='current_merchant')

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ('enable_labels', 'use_pick_up_status',
                                               'use_way_back_status', 'merchant_id')

    def validate_merchant_id(self, attr):
        if not self.instance.merchants.filter(id=attr.id).exists():
            raise serializers.ValidationError('You cannot choose this merchant')
        return attr


class ObserverSerializer(UserSerializer):
    merchant_id = serializers.PrimaryKeyRelatedField(write_only=True, queryset=Merchant.objects.all(), required=False,
                                                     source='current_merchant')

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ('merchant_id',)

    def validate_merchant_id(self, attr):
        if not self.instance.merchants.filter(id=attr.id).exists():
            raise serializers.ValidationError('You cannot choose this merchant')
        return attr


class SubManagerUserSerializer(ManagerSerializer):
    _exclude_fields = ('store_url', 'merchant', 'phone', 'sms_sender', 'pod_email', 'jobs_export_email',
                       'customer_survey', 'reports_frequency')
    sub_branding = SubBrandingSerializer(exclude_fields=_exclude_fields)

    class Meta(ManagerSerializer.Meta):
        fields = ManagerSerializer.Meta.fields + ('sub_branding',)
        read_only_fields = fields
