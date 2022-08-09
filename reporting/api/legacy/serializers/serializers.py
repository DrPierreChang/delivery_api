from __future__ import unicode_literals

from rest_framework import serializers

from base.api.legacy.serializers import DelayedTaskSerializer, SmallUserInfoSerializer
from base.models import Member
from merchant.models import SubBranding
from merchant.validators import MerchantsOwnValidator
from radaro_utils.serializers.fields import ParseDateTimeField, UTCTimestampField
from reporting.model_mapping import serializer_map
from reporting.models import Event, ExportReportInstance
from tasks.mixins.order_status import StatusFilterConditions


class OrderParametersSerializer(serializers.Serializer):
    driver_id = serializers.PrimaryKeyRelatedField(allow_null=True, queryset=Member.all_drivers.all().not_deleted())
    date_from = ParseDateTimeField(force_utc=False)
    date_to = ParseDateTimeField(force_utc=False)
    group = serializers.ChoiceField(allow_null=True, required=False, choices=StatusFilterConditions.available)
    sub_branding_id = serializers.PrimaryKeyRelatedField(allow_null=True, required=False,
                                                         queryset=SubBranding.objects.all(),
                                                         validators=[MerchantsOwnValidator('subbranding')])

    def validate_date_from(self, param):
        if param.tzinfo is None:
            return self.context['request'].user.current_merchant.timezone.localize(param)
        return param

    def validate_date_to(self, param):
        if param.tzinfo is None:
            return self.context['request'].user.current_merchant.timezone.localize(param)
        return param

class OrderResultReportSerializer(serializers.Serializer):
    date = serializers.DateField()
    successful_tasks = serializers.IntegerField()
    unsuccessful_tasks = serializers.IntegerField()
    total_tasks = serializers.IntegerField()


class OrderStatsReportSerializer(serializers.Serializer):
    date = serializers.DateField()
    avg_distance = serializers.FloatField()
    avg_duration = serializers.FloatField()
    finished_tasks = serializers.IntegerField()
    sum_distance = serializers.FloatField()
    sum_duration = serializers.FloatField()


class EventSerializerV2(serializers.ModelSerializer):
    VERSION = 2

    event = serializers.SerializerMethodField()
    initiator = SmallUserInfoSerializer()
    obj_dump = serializers.JSONField()
    type = serializers.SerializerMethodField()
    object = serializers.SerializerMethodField()

    def get_event(self, instance):
        return instance.get_event_display()

    def get_type(self, instance):
        return instance.get_content_type_model()

    def get_object(self, instance):
        if instance.event in [Event.MODEL_CHANGED, Event.CREATED]:
            Serializer = serializer_map.get_for_detailed_dump(type(instance.object), version=self.VERSION)
            return Serializer(instance.object, context=self.context).data
        elif instance.event == Event.DELETED:
            return self.get_detailed_dump(instance)
        return None

    def get_detailed_dump(self, instance):
        if not instance.detailed_dump:
            return instance.detailed_dump
        else:
            return instance.detailed_dump.get('{}'.format(self.VERSION), instance.detailed_dump)

    class Meta:
        fields = ('event', 'obj_dump', 'initiator', 'type', 'object_id', 'object')
        model = Event


class ExportReportSerializer(DelayedTaskSerializer):

    class Meta(DelayedTaskSerializer.Meta):
        model = ExportReportInstance
        fields = DelayedTaskSerializer.Meta.fields + ('file', )


class OfflineHappenedAtSerializer(serializers.Serializer):
    offline_happened_at = UTCTimestampField()


class SMSReportSerializer(serializers.Serializer):
        date_from = ParseDateTimeField(allow_null=True, force_utc=False)
        date_to = ParseDateTimeField(allow_null=True, force_utc=False)


__all__ = ['OrderParametersSerializer', 'OrderResultReportSerializer',
           'OrderStatsReportSerializer',
           'ExportReportSerializer',
           'EventSerializerV2', 'SMSReportSerializer', ]
