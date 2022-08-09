from __future__ import unicode_literals

import re

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from radaro_utils.serializers.mixins import BaseUnpackMixin


class LocationSerializer(serializers.Serializer):

    def validate_location(self, attrs):
        r = re.compile(r'[-+]?[0-9]+\.[0-9]+,\s*[-+]?[0-9]+\.[0-9]+')
        if not r.match(attrs):
            raise ValidationError('Invalid location format.')
        return attrs


class LocationUnpackMixin(BaseUnpackMixin):
    location_class = None
    location_names = None

    def unpack_fields(self, validated_data):
        super(LocationUnpackMixin, self).unpack_fields(validated_data)
        for name in self.location_names:
            if validated_data.get(name, {}) is None:
                continue
            data = validated_data.pop(name, {})
            location = data.get('location', '')
            if location:
                obj, _ = self._get_location_object(location, data)
                validated_data[name] = obj

    def _get_location_object(self, location, data):
        return self.location_class.objects.get_or_create(
            location=location,
            address=data.get('address', ''),
            defaults=data
        )
