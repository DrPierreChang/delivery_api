from operator import itemgetter

from django.utils import timezone

from rest_framework import serializers

from driver.celery_tasks import process_new_location
from driver.models import DriverLocation
from radaro_utils.serializers.fields import UTCTimestampField
from radaro_utils.serializers.validators import ValidateEarlierThanNowConfigurable, ValidateLaterDoesNotExist
from routing.serializers import LocationSerializer


class DriverLocationListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        user = self.context['request'].user.id
        locations = [DriverLocation(member_id=user, **item) for item in
                     sorted(validated_data, key=itemgetter('timestamp'))]
        ValidateLaterDoesNotExist(DriverLocation.objects.filter(member_id=user), 'timestamp')(locations[0].timestamp)
        coordinates = DriverLocation.objects.bulk_create(locations)
        process_new_location.delay(user, coordinates[-1].id)
        return coordinates


class DriverLocationSerializer(LocationSerializer, serializers.ModelSerializer):
    timestamp = UTCTimestampField(required=False, validators=[ValidateEarlierThanNowConfigurable()], default=timezone.now)
    speed = serializers.FloatField(default=0.0)
    accuracy = serializers.FloatField(default=0.0)

    class Meta:
        model = DriverLocation
        exclude = ('member',)
        read_only_fields = ('created_at', 'id', 'improved_location')
        list_serializer_class = DriverLocationListSerializer

    def create(self, validated_data):
        user = self.context['request'].user.id
        # Outside of .validate() to prevent checking when validating list
        ValidateLaterDoesNotExist(DriverLocation.objects.filter(member_id=user), 'timestamp')(validated_data['timestamp'])
        coordinate = DriverLocation.objects.create(member_id=user, **validated_data)
        process_new_location.delay(user, coordinate.id)
        return coordinate


class RetrieveDriverLocationSerializer(DriverLocationSerializer):
    location = serializers.SerializerMethodField()

    # If we retrieve location, good solution is to incapsulate real field
    # Front-end really doesn't need to know is it real or improved
    def get_location(self, instance):
        return instance.improved_location or instance.location
