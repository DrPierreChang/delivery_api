from rest_framework import serializers

from radaro_utils.serializers.mixins import SerializerExcludeFieldsMixin
from radaro_utils.serializers.validators import LaterThenNowValidator
from route_optimisation.api.fields import CurrentMerchantDefault
from tasks.models import Order, Pickup

from ..location import WebLocationSerializer
from .deliver import PhotoConfirmationSerializer


class PickupCustomerSerializer(serializers.ModelSerializer):
    merchant = serializers.HiddenField(default=CurrentMerchantDefault())

    class Meta:
        model = Pickup
        fields = ('merchant', 'id', 'name', 'phone_number', 'email')
        extra_kwargs = {
            'phone_number': {'source': 'phone', 'default': ''},
            'email': {'default': ''},
        }

    def create(self, validated_data):
        if validated_data is None:
            return None

        customer = Pickup.objects.filter(**validated_data).last()
        if customer:
            return customer

        return super().create(validated_data)

    def update(self, instance, validated_data):
        if validated_data is None:
            return None

        if instance:
            validated_data = {
                'merchant_id': instance.merchant_id,
                'name': validated_data.get('name', instance.name),
                'phone': validated_data.get('phone', instance.phone),
                'email': validated_data.get('email', instance.email),
            }
        return self.create(validated_data)


class SignaturePickUpConfirmationSerializer(serializers.ModelSerializer):
    url = serializers.ImageField(source='pick_up_confirmation_signature', read_only=True)

    class Meta:
        model = Order
        fields = ('url',)


class PickUpConfirmationSerializer(serializers.ModelSerializer):
    photo = PhotoConfirmationSerializer(many=True, source='pick_up_confirmation_photos', read_only=True)
    signature = SignaturePickUpConfirmationSerializer(source='*', read_only=True)

    class Meta:
        model = Order
        fields = ('photo', 'signature', 'comment')
        extra_kwargs = {
            'comment': {'source': 'pick_up_confirmation_comment'},
        }


class PickupWebOrderSerializer(SerializerExcludeFieldsMixin, serializers.ModelSerializer):
    customer = PickupCustomerSerializer(source='pickup', allow_null=True, required=False)
    address = WebLocationSerializer(source='pickup_address', allow_null=True)
    confirmation = PickUpConfirmationSerializer(required=False, source='*')

    class Meta:
        model = Order
        fields = ('customer', 'address', 'after', 'before', 'confirmation')
        extra_kwargs = {
            'after': {'source': 'pickup_after', 'validators': [LaterThenNowValidator()]},
            'before': {'source': 'pickup_before', 'validators': [LaterThenNowValidator()]},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if self.root.instance:
            is_pickup_address = bool(attrs.get('pickup_address', self.root.instance.pickup_address_id))
        else:
            is_pickup_address = bool(attrs.get('pickup_address', None))

        if not is_pickup_address:
            attrs['pickup'] = None
            attrs['pickup_after'] = None
            attrs['pickup_before'] = None

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if 'confirmation' in data:
            is_confirmation = bool(data['confirmation']['photo'] and data['confirmation']['signature']['url'])
            merchant = instance.merchant

            if not merchant.enable_pick_up_confirmation and not is_confirmation:
                data.pop('confirmation', None)

        return data
