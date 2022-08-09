from django.contrib.auth import get_user_model
from django.db import transaction

from rest_framework import serializers

from base.api.mobile.serializers.v1.members import NestedAvatarSerializer
from base.models import Member
from merchant.api.web.hubs.serializers import HubLocationSerializer, WebHubSerializer
from merchant.models import Hub
from radaro_utils.serializers.mobile.fields import RadaroMobilePhoneField
from radaro_utils.serializers.web.fields import WebPrimaryKeyWithMerchantRelatedField
from reporting.context_managers import track_fields_for_offline_changes, track_fields_on_change

from .current_path import WebCurrentPathDriverSerializer
from .location import WebDriverLocationSerializer
from .vehicle import WebVehicleSerializer


class WebDefaultDriverSerializer(serializers.Serializer):
    starting_hub = WebHubSerializer(allow_null=True, read_only=True)
    starting_hub_id = WebPrimaryKeyWithMerchantRelatedField(
        source='starting_hub', queryset=Hub.objects.all(), allow_null=True, write_only=True)
    ending_hub = WebHubSerializer(allow_null=True, read_only=True)
    ending_hub_id = WebPrimaryKeyWithMerchantRelatedField(
        source='ending_hub', queryset=Hub.objects.all(), allow_null=True, write_only=True)
    ending_point = HubLocationSerializer(required=False, allow_null=True)


class WorkStatusField(serializers.ChoiceField):
    def __init__(self, **kwargs):
        choices = Member.work_status_choices
        super().__init__(choices, **kwargs)

    def to_representation(self, value):
        if isinstance(self.parent.instance, Member):
            return self.parent.instance.get_work_status_for_manager()
        else:
            return super().to_representation(value)


class WebDriverSerializer(serializers.ModelSerializer):
    phone_number = RadaroMobilePhoneField(source='phone', read_only=True)
    merchant_id = serializers.IntegerField(source='current_merchant_id', read_only=True)

    merchant_position = serializers.CharField(read_only=True)
    sod_checklist_failed = serializers.SerializerMethodField()
    eod_checklist_failed = serializers.SerializerMethodField()
    active_orders_count = serializers.IntegerField(read_only=True)
    work_status = WorkStatusField()

    avatar = NestedAvatarSerializer(source='*', read_only=True)
    vehicle = WebVehicleSerializer(source='car')
    last_location = WebDriverLocationSerializer(read_only=True)
    current_path = WebCurrentPathDriverSerializer(read_only=True)
    skill_set_ids = serializers.PrimaryKeyRelatedField(many=True, source='skill_sets', read_only=True)
    default_order_values = WebDefaultDriverSerializer(source='*')

    class Meta:
        model = get_user_model()
        fields = (
            'id', 'member_id', 'email', 'first_name', 'last_name', 'phone_number', 'avatar', 'vehicle', 'merchant_id',
            'status', 'work_status', 'has_internet_connection',
            'merchant_position', 'sod_checklist_failed', 'eod_checklist_failed', 'active_orders_count',
            'last_location', 'current_path', 'skill_set_ids', 'default_order_values', 'deleted',
        )
        editable_fields = {
            'vehicle', 'default_order_values', 'work_status',
        }
        read_only_fields = list(set(fields) - set(editable_fields))

    def __init__(self, instance=None, *args, **kwargs):
        super().__init__(instance, *args, **kwargs)

        if isinstance(instance, Member):
            merchant = instance.current_merchant
        else:
            merchant = self.context['request'].user.current_merchant

        if not merchant.enable_job_capacity:
            del self.fields['vehicle'].fields['capacity']
        if not merchant.use_hubs:
            del self.fields['default_order_values'].fields['starting_hub']
            del self.fields['default_order_values'].fields['starting_hub_id']
            del self.fields['default_order_values'].fields['ending_hub']
            del self.fields['default_order_values'].fields['ending_hub_id']
        if not merchant.enable_skill_sets:
            del self.fields['skill_set_ids']

    def get_sod_checklist_failed(self, obj):
        if getattr(obj, 'sod_checklists', False):
            return obj.sod_checklists[0].is_correct is False
        return False

    def get_eod_checklist_failed(self, obj):
        if hasattr(obj, 'eod_checklists') and obj.eod_checklists:
            return obj.eod_checklists[0].is_correct is False
        return False

    def _get_data_for_event(self, instance):
        location = instance.last_location.location
        if not location:
            return None
        return {
            'additional_info_for_fields': {
                'work_status': {
                    'last_location': {
                        'location': location,
                    }
                }
            }
        }

    def update(self, instance, validated_data):
        work_status = validated_data.pop('work_status', None)

        with transaction.atomic():
            if validated_data:
                with track_fields_on_change(instance, initiator=self.context['request'].user):
                    if 'car' in validated_data:
                        vehicle = self.fields['vehicle']
                        validated_data['car'] = vehicle.update(instance.car, validated_data['car'])
                    if 'ending_point' in validated_data:
                        validated_data['ending_point'] = self.fields['default_order_values']['ending_point'].create(
                            validated_data['ending_point'])
                    instance = super().update(instance, validated_data)

            # Change of work status requires generation of special events
            if work_status:
                with track_fields_for_offline_changes(instance, self, self.context['request']) as event_fields:
                    instance.set_availability_status(work_status, self.context['request'].user)
                    event_fields['instance'] = instance
                    event_fields['additional_data_for_event'] = self._get_data_for_event(instance)

        return instance
