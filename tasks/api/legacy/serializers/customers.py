from rest_framework import serializers

from tasks.models import Customer, Pickup


class BaseCustomerSerializer(serializers.ModelSerializer):
    unique_together_fields = ('email', 'name', 'phone')

    class Meta:
        model = Customer
        fields = ('id', 'email', 'name', 'phone')
        read_only_fields = ('id',)


class CustomerSerializer(BaseCustomerSerializer):
    class Meta(BaseCustomerSerializer.Meta):
        fields = BaseCustomerSerializer.Meta.fields + ('id',)
        extra_kwargs = {
            'email': {'default': ''},
            'phone': {'default': ''},
        }

    def validate_email(self, attr):
        if not attr:
            return ''
        return attr

    def validate_phone(self, attr):
        if not attr:
            return ''
        return attr


class PickupSerializer(serializers.ModelSerializer):
    unique_together_fields = ('name', 'email', 'phone')

    class Meta:
        model = Pickup
        exclude = ('merchant',)
        read_only_fields = ('id',)
        extra_kwargs = {
            'email': {'default': ''},
            'phone': {'default': ''},
        }
