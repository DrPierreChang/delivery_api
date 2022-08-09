from rest_framework import serializers

from radaro_utils.serializers.mobile.serializers import RadaroMobileModelSerializer
from tasks.models import Customer, Pickup

from ...fields.v1 import CurrentMerchantDefault


class CustomerSerializer(RadaroMobileModelSerializer):
    merchant = serializers.HiddenField(default=CurrentMerchantDefault())

    class Meta:
        model = Customer
        fields = ('name', 'phone_number', 'email', 'merchant')
        extra_kwargs = {
            'phone_number': {'source': 'phone', 'default': ''},
            'email': {'default': ''},
        }

    def validate_phone_number(self, attr):
        if not attr:
            return ''
        return attr

    def validate_email(self, attr):
        if not attr:
            return ''
        return attr

    def create(self, validated_data):
        customer = Customer.objects.filter(**validated_data).last()
        if customer:
            return customer

        return super().create(validated_data)


class PickupCustomerSerializer(RadaroMobileModelSerializer):
    merchant = serializers.HiddenField(default=CurrentMerchantDefault())

    class Meta:
        model = Pickup
        fields = ('name', 'phone_number', 'email', 'merchant')
        extra_kwargs = {
            'phone_number': {'source': 'phone', 'default': ''},
            'email': {'default': ''},
        }

    def create(self, validated_data):
        if validated_data is None:
            return None

        pickup_customer = Pickup.objects.filter(**validated_data).last()
        if pickup_customer:
            return pickup_customer

        return super().create(validated_data)
