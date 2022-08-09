from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from documents.models import OrderConfirmationDocument, Tag

from .fields import CustomKeyWithMerchantRelatedField


class CreateDriverOrderConfirmationDocumentSerializer(serializers.ModelSerializer):
    document = serializers.FileField(required=True)
    tag_id = serializers.ManyRelatedField(
        required=False,
        child_relation=CustomKeyWithMerchantRelatedField(
            queryset=Tag.objects.all(),
            required=False
        ),
        source='tags',
    )

    class Meta:
        model = OrderConfirmationDocument
        fields = ('document', 'name', 'tag_id')
        extra_kwargs = {'name': {'required': True}}

    def validate_name(self, attr):
        if self.context['order'].order_confirmation_documents.filter(name=attr).exists():
            raise serializers.ValidationError(
                _('The document named "{name}" is already uploaded to the server.'.format(name=attr))
            )
        return attr

    def validate(self, attrs):
        return {'order': self.context['order'], **attrs}
