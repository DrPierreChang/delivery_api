from rest_framework import serializers

from radaro_utils.geo import AddressGeocoder
from routing.google import GoogleClient
from routing.serializers.fields import LatLngLocation


class PrimaryAddressSerializer(serializers.Serializer):
    location = LatLngLocation(required=False)
    address = serializers.CharField(required=False)


class AbstractAddressSerializer(serializers.ModelSerializer):
    primary_address = PrimaryAddressSerializer(source='*')

    class Meta:
        fields = ('primary_address',)

    def validate(self, attrs):
        location = attrs.get('location', None)
        address = attrs.get('address', None)

        if location is None:
            if address is None:
                raise serializers.ValidationError('You should specify either location or address')

            geocoded_from_address = self._process_address_field(address)
            if geocoded_from_address is None:
                raise serializers.ValidationError({'address': 'Address not found.'})

            attrs.update(geocoded_from_address)

        if address is None:
            attrs['address'] = attrs['location']

        return attrs

    def _process_address_field(self, address):
        user = self.context.get('request').user
        regions = user.current_merchant.countries if hasattr(user, 'merchant') else ['AU']
        with GoogleClient.track_merchant(user.current_merchant):
            return AddressGeocoder().geocode(address, regions, user.current_merchant.language)
