from rest_framework import serializers

from route_optimisation.api.fields import CurrentMerchantDefault
from tasks.models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    merchant = serializers.HiddenField(default=CurrentMerchantDefault())

    class Meta:
        model = Customer
        fields = ('merchant', 'id', 'name', 'phone_number', 'email')
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
