from rest_framework import serializers

from documents.api.mobile.serializers import TagSerializer
from documents.models import OrderConfirmationDocument
from radaro_utils.serializers.mixins import SerializerExcludeFieldsMixin
from radaro_utils.serializers.validators import LaterThenNowValidator
from tasks.models import Order

from ..customer import CustomerSerializer
from ..location import WebLocationSerializer


class PhotoConfirmationSerializer(serializers.Serializer):
    url = serializers.ImageField(required=False, allow_null=True, source='image')


class SignatureConfirmationSerializer(serializers.ModelSerializer):
    url = serializers.ImageField(source='confirmation_signature', read_only=True)

    class Meta:
        model = Order
        fields = ('url',)


class DocumentConfirmationSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True)

    class Meta:
        model = OrderConfirmationDocument
        fields = ('id', 'document', 'name', 'tags')
        read_only_fields = ('id',)


class ConfirmationSerializer(serializers.ModelSerializer):
    photo = PhotoConfirmationSerializer(many=True, source='order_confirmation_photos', read_only=True)
    signature = SignatureConfirmationSerializer(source='*', read_only=True)
    documents = DocumentConfirmationSerializer(source='order_confirmation_documents', many=True, read_only=True)

    class Meta:
        model = Order
        fields = ('photo', 'signature', 'comment', 'documents')
        extra_kwargs = {
            'comment': {'source': 'confirmation_comment'},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data:
            merchant = instance.merchant
            if not merchant.enable_delivery_confirmation_documents and not data.get('documents'):
                data.pop('documents', None)
        return data


class SignaturePreConfirmationSerializer(serializers.ModelSerializer):
    url = serializers.ImageField(source='pre_confirmation_signature', read_only=True)

    class Meta:
        model = Order
        fields = ('url',)


class PreConfirmationSerializer(serializers.ModelSerializer):
    photo = PhotoConfirmationSerializer(many=True, source='pre_confirmation_photos', read_only=True)
    signature = SignaturePreConfirmationSerializer(source='*', read_only=True)

    class Meta:
        model = Order
        fields = ('photo', 'signature', 'comment')
        extra_kwargs = {
            'comment': {'source': 'pre_confirmation_comment'},
        }


class DeliverWebOrderSerializer(SerializerExcludeFieldsMixin, serializers.ModelSerializer):
    customer = CustomerSerializer()
    address = WebLocationSerializer(source='deliver_address')
    pre_confirmation = PreConfirmationSerializer(required=False, source='*', read_only=True)
    confirmation = ConfirmationSerializer(required=False, source='*', read_only=True)

    class Meta:
        model = Order
        fields = ('customer', 'address', 'after', 'before', 'pre_confirmation', 'confirmation')
        extra_kwargs = {
            'after': {'source': 'deliver_after', 'validators': [LaterThenNowValidator()]},
            'before': {'source': 'deliver_before', 'validators': [LaterThenNowValidator()]},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        merchant = instance.merchant

        if 'pre_confirmation' in data:
            is_pre_confirmation = bool(
                data['pre_confirmation']['photo'] and data['pre_confirmation']['signature']['url']
            )
            if not merchant.enable_delivery_pre_confirmation and not is_pre_confirmation:
                data.pop('pre_confirmation', None)

        if 'confirmation' in data:
            is_confirmation = bool(data['confirmation']['photo'] and data['confirmation']['signature']['url'])
            if not merchant.enable_delivery_confirmation and not is_confirmation:
                data.pop('confirmation', None)

        return data
