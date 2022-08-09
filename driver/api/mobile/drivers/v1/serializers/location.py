from operator import itemgetter

from django.utils import timezone

from rest_framework import serializers

from driver.celery_tasks import process_new_location
from driver.models import DriverLocation
from radaro_utils.serializers.fields import UTCTimestampField
from radaro_utils.serializers.validators import ValidateEarlierThanNowConfigurable, ValidateLaterDoesNotExist
from routing.serializers.fields import LatLngLocation


class MobileDriverLocationSerializer(serializers.ModelSerializer):
    member = serializers.HiddenField(default=serializers.CurrentUserDefault())
    offline = serializers.HiddenField(default=False)
    location = LatLngLocation()
    timestamp = UTCTimestampField(required=False, validators=[ValidateEarlierThanNowConfigurable()],
                                  default=timezone.now)
    speed = serializers.FloatField(default=0.0)
    accuracy = serializers.FloatField(default=0.0)

    class Meta:
        model = DriverLocation
        fields = (
            'member', 'offline', 'location', 'address', 'description', 'accuracy', 'speed', 'bearing', 'timestamp',
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if hasattr(self.root, '_validate_later'):
            validator = self.root._validate_later
        else:
            validator = ValidateLaterDoesNotExist(DriverLocation.objects.filter(member=attrs['member']), 'timestamp')
        validator(attrs['timestamp'])

        return attrs

    def create(self, validated_data):
        driver_location = super().create(validated_data)
        process_new_location.delay(validated_data['member'].id, driver_location.id)
        return driver_location


class OfflineMobileDriverLocationSerializer(MobileDriverLocationSerializer):
    offline = serializers.HiddenField(default=True)
    timestamp = UTCTimestampField(required=True, validators=[ValidateEarlierThanNowConfigurable()])


class HistoryMobileDriverLocationSerializer(serializers.Serializer):
    offline_history = OfflineMobileDriverLocationSerializer(many=True)

    class Meta:
        model = DriverLocation
        fields = ('offline_history',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.context['request'].user
        self._validate_later = ValidateLaterDoesNotExist(DriverLocation.objects.filter(member=user), 'timestamp')

    def create(self, validated_data):
        offline_history = validated_data['offline_history']
        driver_location = [DriverLocation(**item) for item in sorted(offline_history, key=itemgetter('timestamp'))]
        driver_location = DriverLocation.objects.bulk_create(driver_location)

        user = self.context['request'].user.id
        process_new_location.delay(user, driver_location[-1].id)

        return driver_location
