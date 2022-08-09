from django.utils import timezone

from rest_framework import serializers

from merchant.models import Hub
from merchant.validators import MerchantsOwnValidator
from route_optimisation.api.mobile.v1.serializers import CreateRouteOptimisationSerializer
from route_optimisation.const import HubOptions


class LegacyCreateRouteOptimisationSerializer(serializers.Serializer):
    start_hub = serializers.PrimaryKeyRelatedField(
        queryset=Hub.objects.all(),
        required=False,
        allow_null=True,
        validators=[MerchantsOwnValidator('hub')],
    )
    end_hub = serializers.PrimaryKeyRelatedField(
        queryset=Hub.objects.all(),
        required=False,
        allow_null=True,
        validators=[MerchantsOwnValidator('hub')],
    )
    start_location = serializers.DictField(required=False, allow_null=True)
    end_location = serializers.DictField(required=False, allow_null=True)

    class Meta:
        fields = ('start_hub', 'end_hub', 'start_location', 'end_location',)

    def create(self, validated_data):
        user = self.context['request'].user
        start_hub = validated_data.get('start_hub', None)
        end_hub = validated_data.get('end_hub', None)
        start_location = validated_data.get('start_location', None)
        end_location = validated_data.get('end_location', None)
        start_place = (start_hub and HubOptions.START_HUB.hub_location) \
            or (start_location and HubOptions.START_HUB.driver_location)\
            or HubOptions.START_HUB.default_hub
        end_place = (end_hub and HubOptions.END_HUB.hub_location) \
            or (end_location and HubOptions.END_HUB.driver_location)\
            or HubOptions.END_HUB.default_hub
        data = {
            'day': timezone.now().astimezone(user.current_merchant.timezone).date(),
            'options': {
                'start_hub': (start_hub and start_hub.id) or None,
                'start_location': start_location,
                'start_place': start_place,
                'end_hub': (end_hub and end_hub.id) or None,
                'end_location': end_location,
                'end_place': end_place,
            }
        }
        serializer = CreateRouteOptimisationSerializer(data=data, context=dict(self.context, no_sync_push=True))
        serializer.is_valid(raise_exception=True)
        return serializer.save()
