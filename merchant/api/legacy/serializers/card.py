from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.settings import api_settings

import stripe
from pinax.stripe.actions import charges, customers, sources
from pinax.stripe.models import Card
from stripe.error import CardError, InvalidRequestError


class CreateCardSerializer(serializers.Serializer):
    number = serializers.CharField()
    exp_month = serializers.IntegerField()
    exp_year = serializers.IntegerField()
    cvc = serializers.CharField()

    def save(self, **kwargs):
        data = self.validated_data
        try:
            token = stripe.Token.create(card=data)
        except CardError as error:
            raise ValidationError(error.message)
        user = self.context['request'].user
        customer = user.customer if hasattr(user, 'customer') else customers.create(user=user)
        try:
            card = sources.create_card(customer=customer, token=token['id'])
            customers.set_default_source(customer, card.stripe_id)
        except (CardError, InvalidRequestError) as error:
            raise ValidationError(error.message)
        return card


class CardSerializer(serializers.ModelSerializer):

    class Meta:
        model = Card
        fields = ('id', 'created_at', 'brand', 'country', 'exp_month', 'exp_year', 'last4', 'customer')
        read_only_fields = ('created_at', 'brand', 'country', 'last4', 'customer')


class ChargeSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_amount(self, value):
        if value <= 0:
            raise ValidationError('Invalid positive integer')
        return value

    def make_charge(self, card):
        amount = self.validated_data['amount']
        request = self.context.get('request')
        try:
            charges.create(
                amount=amount,
                customer=card.customer.stripe_id,
                source=card.stripe_id,
                currency="aud",
                description="Paid by {}".format(request.user)
            )
            request.user.current_merchant.change_balance(amount)
        except CardError as exc:
            raise ValidationError({api_settings.NON_FIELD_ERRORS_KEY: [exc.message]})
