from __future__ import absolute_import

from rest_framework import serializers

from tasks.utils import StringAddressToOrderLocation


class StringAddressField(serializers.Field):
    def to_internal_value(self, data: tuple):
        # address and address_2 are separate strings
        if not self.allow_empty and not data[0]:
            raise serializers.ValidationError('Address cannot be empty.')

        value = StringAddressToOrderLocation().to_order_location(data, self.context.get('user'))
        if value is None:
            raise serializers.ValidationError('Address not found.')
        return value

    def to_representation(self, value):
        return str(value)

    def __init__(self, allow_empty=True, *args, **kwargs):
        super(StringAddressField, self).__init__(*args, **kwargs)
        self.allow_empty = allow_empty
