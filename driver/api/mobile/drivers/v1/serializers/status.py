from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils.functional import cached_property

from rest_framework import serializers

from base.models import Member
from driver.models import DriverLocation
from radaro_utils.exceptions import TimeMismatchingError
from radaro_utils.serializers.fields import UTCTimestampField
from reporting.context_managers import track_fields_for_offline_changes
from reporting.models import Event
from routing.serializers.fields import LatLngLocation


class DriverStatusLocationSerializer(serializers.ModelSerializer):
    location = LatLngLocation()

    class Meta:
        model = DriverLocation
        fields = ('location',)


class UpdateDriverStatusMixin(serializers.Serializer):
    location = DriverStatusLocationSerializer(write_only=True, required=False, allow_null=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if 'location' in attrs and attrs['location'] is None:
            del attrs['location']
        return attrs

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
            instance.set_availability_status(validated_data['work_status'], request.user)
            event_fields['instance'] = instance
            event_fields['additional_data_for_event'] = self._get_data_for_event(instance, validated_data)
        return instance


class DriverOfflineStatusSerializer(UpdateDriverStatusMixin):
    work_status = serializers.ChoiceField(required=True, choices=Member.work_status_choices)
    offline_happened_at = UTCTimestampField(write_only=True, required=True)

    @cached_property
    def last_happened_at(self):
        driver_content_type = ContentType.objects.get_for_model(Member)
        driver = self.root.instance

        last_event = Event.objects.filter(
            object_id=driver.id,
            content_type=driver_content_type,
            event=Event.CHANGED,
            field='work_status',
        ).order_by('-happened_at').first()

        return last_event.happened_at if last_event else None

    def validate_offline_happened_at(self, attr):
        if self.last_happened_at and attr < self.last_happened_at:
            raise TimeMismatchingError(
                reason='The new event must be later than the last event',
                last_item_time=self.last_happened_at,
            )
        return attr


class DriverStatusSerializer(UpdateDriverStatusMixin):
    work_status = serializers.ChoiceField(required=False, choices=Member.work_status_choices)
    offline_history = DriverOfflineStatusSerializer(many=True, write_only=True, required=False, default=[])

    def update(self, instance, validated_data):
        offline_history = sorted(validated_data['offline_history'], key=lambda item: item['offline_happened_at'])

        with transaction.atomic():
            for item in offline_history:
                instance = self.fields['offline_history'].child.update(instance, item)
            if 'work_status' in validated_data:
                instance = super().update(instance, validated_data)

        return instance
