from __future__ import absolute_import

import re

from rest_framework import serializers
from rest_framework.exceptions import ValidationError


class LocationSerializer(serializers.Serializer):

    def validate_location(self, attrs):
        r = re.compile(r'^[-+]?[0-9]+\.[0-9]+,\s*[-+]?[0-9]+\.[0-9]+$')
        if not r.match(attrs):
            raise ValidationError('Invalid location format.')
        return attrs
