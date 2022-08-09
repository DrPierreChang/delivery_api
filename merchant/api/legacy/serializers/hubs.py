from __future__ import absolute_import

from rest_framework import serializers

from merchant.models import Hub, HubLocation
from reporting.api.legacy.serializers.delta import DeltaSerializer
from reporting.model_mapping import serializer_map
from routing.serializers import LocationSerializer, LocationUnpackMixin
from routing.serializers.fields import LatLngLocation


class HubLocationSerializer(LocationSerializer, serializers.ModelSerializer):
    location = serializers.CharField(required=True)

    class Meta:
        model = HubLocation
        fields = ('id', 'address', 'location', 'description')
        read_only_fields = ('id', )
        validators = []


class HubLocationSerializerV2(HubLocationSerializer):
    location = LatLngLocation(required=True)

    class Meta(HubLocationSerializer.Meta):
        pass


@serializer_map.register_serializer_for_detailed_dump(version=1)
class HubSerializer(LocationUnpackMixin, serializers.ModelSerializer):
    location_class = HubLocation
    location_names = ('location', )

    phone = serializers.CharField(allow_blank=True,
                                  allow_null=True,
                                  required=False)
    location = HubLocationSerializer(required=True)

    class Meta:
        model = Hub
        fields = ('id', 'name', 'phone', 'location', 'merchant', 'status')
        read_only_fields = ('id', 'merchant', )


@serializer_map.register_serializer
class HubDeltaSerializer(DeltaSerializer):
    class Meta(DeltaSerializer.Meta):
        model = Hub


@serializer_map.register_serializer_for_detailed_dump(version='web')
@serializer_map.register_serializer_for_detailed_dump(version=2)
class HubSerializerV2(HubSerializer):
    location = HubLocationSerializerV2(required=True)

    class Meta(HubSerializer.Meta):
        pass


class ExternalHubSerializer(serializers.ModelSerializer):
    location = HubLocationSerializer()

    class Meta:
        model = Hub
        fields = ('id', 'name', 'location', 'phone',  'merchant')
