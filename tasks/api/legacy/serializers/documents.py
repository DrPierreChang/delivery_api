from rest_framework import serializers

from documents.models import OrderConfirmationDocument, Tag


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ('id', 'name')
        read_only_fields = ('id',)


class OrderConfirmationDocumentSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True)

    class Meta:
        model = OrderConfirmationDocument
        fields = ('id', 'document', 'name', 'tags')
        read_only_fields = ('id',)


class CreateOrderConfirmationDocumentSerializer(serializers.ModelSerializer):
    document = serializers.FileField(required=True)
    tag = serializers.ManyRelatedField(
        required=False,
        child_relation=serializers.PrimaryKeyRelatedField(
            queryset=Tag.objects.all(),
            required=False
        ),
        source='tags',
    )

    class Meta:
        model = OrderConfirmationDocument
        fields = ('document', 'name', 'tag')
        extra_kwargs = {'name': {'required': True}}

    def validate_tag(self, attrs):
        request = self.context.get('request')

        if any(attr.merchant_id != request.user.current_merchant_id for attr in attrs):
            raise serializers.ValidationError("This is not merchant's tags")

        return attrs

    def validate(self, attrs):
        attrs['order'] = self.context['order']
        return attrs

    def create(self, validated_data):
        exists_order = self.context['order'].order_confirmation_documents.filter(name=validated_data['name']).first()
        if exists_order:
            return exists_order

        return super().create(validated_data)
