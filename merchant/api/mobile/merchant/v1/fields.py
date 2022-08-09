from rest_framework import serializers

from merchant.models import Merchant


class MerchantDistanceChoiceField(serializers.ChoiceField):
    def to_representation(self, value):
        return {
            'type_value': value,
            'type': Merchant.distance_aliases[value],
        }
