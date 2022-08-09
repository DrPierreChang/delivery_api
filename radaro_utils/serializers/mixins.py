from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from radaro_utils.geo import AddressGeocoder
from radaro_utils.serializers.mobile.serializers import RadaroMobileModelSerializer
from routing.google import GoogleClient
from routing.serializers.fields import LatLngLocation


class BaseUnpackMixin(object):

    def unpack_fields(self, validated_data):
        pass

    def create(self, validated_data):
        self.unpack_fields(validated_data)
        return super(BaseUnpackMixin, self).create(validated_data)

    def update(self, instance, validated_data):
        self.unpack_fields(validated_data)
        return super(BaseUnpackMixin, self).update(instance, validated_data)


class AbstractAddressSerializer(RadaroMobileModelSerializer):
    location = LatLngLocation(required=False)

    class Meta:
        fields = ('address', 'location')

    def validate(self, attrs):
        location = attrs.get('location', None)
        address = attrs.get('address', None)

        if location is None:
            if address is None:
                raise serializers.ValidationError(_('You should specify either location or address'))

            geocoded_from_address = self._process_address_field(address)
            if geocoded_from_address is None:
                raise serializers.ValidationError({'address': _('Address not found.')})

            attrs.update(geocoded_from_address)

        if address is None:
            attrs['address'] = attrs['location']

        return attrs

    def _process_address_field(self, address):
        user = self.context.get('request').user
        regions = user.current_merchant.countries if hasattr(user, 'merchant') else ['AU']
        with GoogleClient.track_merchant(user.current_merchant):
            return AddressGeocoder().geocode(address, regions)


class SerializerExcludeFieldsMixin(object):

    def __init__(self, *args, **kwargs):

        exclude_fields = kwargs.pop('exclude_fields', [])

        super(SerializerExcludeFieldsMixin, self).__init__(*args, **kwargs)
        for field_name in exclude_fields:
            self.fields.pop(field_name, None)
