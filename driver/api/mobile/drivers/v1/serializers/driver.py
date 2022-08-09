from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from rest_framework import serializers

from base.api.legacy.serializers import CarUnpackMixin
from base.api.mobile.serializers.v1.members import ManagerSerializer, NestedAvatarSerializer
from base.api.mobile.serializers.v1.vehicles import VehicleSerializer
from base.models import Member
from driver.api.mobile.drivers.v1.serializers.validators import MemberUniqueValidator
from merchant.api.legacy.serializers.skill_sets import SkillSetDestroyValidationMixin
from merchant.api.mobile.serializers import HubLocationSerializer
from merchant.models import Hub, SkillSet
from radaro_utils.serializers.mobile.fields import (
    RadaroMobileImageField,
    RadaroMobilePhoneField,
    RadaroMobilePrimaryKeyRelatedField,
    RadaroMobilePrimaryKeyWithMerchantRelatedField,
)
from radaro_utils.serializers.mobile.serializers import RadaroMobileModelSerializer


class ListDriverSerializer(RadaroMobileModelSerializer):
    avatar = NestedAvatarSerializer(source='*', read_only=True)
    skill_set_ids = RadaroMobilePrimaryKeyRelatedField(many=True, source='skill_sets', read_only=True)

    class Meta:
        model = get_user_model()
        fields = ('id', 'first_name', 'last_name', 'avatar', 'skill_set_ids')


class ImageDriverSerializer(serializers.ModelSerializer):
    avatar = RadaroMobileImageField()

    class Meta:
        model = get_user_model()
        fields = ('avatar',)


class OrderValuesDriverSerializer(RadaroMobileModelSerializer):
    wayback_hub_ids = RadaroMobilePrimaryKeyWithMerchantRelatedField(
        many=True,
        queryset=Hub.objects.all(),
        required=False,
        source='wayback_hubs',
    )

    starting_hub_id = RadaroMobilePrimaryKeyWithMerchantRelatedField(
        source='starting_hub', queryset=Hub.objects.all(), allow_null=True)
    ending_hub_id = RadaroMobilePrimaryKeyWithMerchantRelatedField(
        source='ending_hub', queryset=Hub.objects.all(), allow_null=True)
    ending_point = HubLocationSerializer(required=False, allow_null=True)

    class Meta:
        model = get_user_model()
        fields = ('wayback_hub_ids', 'starting_hub_id', 'ending_hub_id', 'ending_point')


class DriverSerializer(CarUnpackMixin, SkillSetDestroyValidationMixin, RadaroMobileModelSerializer):
    car_field_names = ('car',)

    cluster_number = serializers.SerializerMethodField()
    avatar = NestedAvatarSerializer(source='*', read_only=True)
    vehicle = VehicleSerializer(source='car')
    phone_number = RadaroMobilePhoneField(source='phone')
    manager = serializers.SerializerMethodField()
    merchant_id = serializers.IntegerField(source='current_merchant_id', read_only=True)
    skill_set_ids = RadaroMobilePrimaryKeyWithMerchantRelatedField(
        many=True,
        queryset=SkillSet.objects.all(),
        required=False,
        source='skill_sets',
    )
    default_order_values = OrderValuesDriverSerializer(source='*')

    def validate_skill_set_ids(self, skill_sets):
        # The validator is necessary so that secret skill sets do not raise an error and are simply ignored
        return [skill_set for skill_set in skill_sets if not skill_set.is_secret]

    class Meta:
        model = get_user_model()
        fields = ('id', 'cluster_number', 'email', 'first_name', 'last_name', 'vehicle', 'avatar', 'language',
                  'work_status', 'phone_number', 'manager', 'merchant_id', 'skill_set_ids', 'default_order_values')
        read_only_fields = ('id', 'avatar', 'work_status', 'manager', 'merchant_id', 'cluster_number')
        validators = [MemberUniqueValidator()]

    def get_manager(self, instance):
        if instance.current_merchant:
            manager = instance.current_merchant.member_set.filter(Q(role=Member.MANAGER) | Q(role=Member.ADMIN)) \
                .order_by('-role').first()
            group_manager = instance.current_merchant.group_managers.filter(role__in=[Member.MANAGER, Member.ADMIN]) \
                .order_by('-role').first()
            manager = manager or group_manager
            return ManagerSerializer(instance=manager, context=self.context).data

    def get_cluster_number(self, instance):
        return settings.CLUSTER_NUMBER

    def validate(self, attrs):
        if 'skill_sets' in attrs:
            skill_sets = {skill.id for skill in attrs.get('skill_sets')}
            skill_sets_to_delete = self.instance.skill_sets.filter(is_secret=False).exclude(id__in=skill_sets)

            if skill_sets_to_delete:
                self._validate_on_destroy(
                    skill_sets_to_delete,
                    self.instance.order_set.all().annotate_job_type_for_skillsets(skill_sets_to_delete),
                    background_notification=True
                )
        return super().validate(attrs)

    def update(self, instance, validated_data):
        with transaction.atomic():
            if 'skill_sets' in validated_data:
                new_skills = {skill.id for skill in validated_data.pop('skill_sets')}
                existing_skills = set(instance.skill_sets.filter(is_secret=False).values_list('id', flat=True))
                instance.skill_sets.remove(*(existing_skills - new_skills))
                instance.skill_sets.add(*(new_skills - existing_skills))

            if 'wayback_hubs' in validated_data:
                new_wayback_hubs = {hub.id for hub in validated_data.pop('wayback_hubs')}
                existing_wayback_hubs = set(instance.wayback_hubs.values_list('id', flat=True))
                instance.wayback_hubs.remove(*(existing_wayback_hubs - new_wayback_hubs))
                instance.wayback_hubs.add(*(new_wayback_hubs - existing_wayback_hubs))

            if 'ending_point' in validated_data:
                validated_data['ending_point'] = self.fields['default_order_values']['ending_point']\
                    .create(validated_data['ending_point'])

            return super().update(instance, validated_data)
