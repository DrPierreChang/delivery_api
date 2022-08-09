from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from documents.api.mobile.serializers import TagSerializer
from documents.models import OrderConfirmationDocument
from radaro_utils.serializers.mobile.fields import NullResultMixin, RadaroMobileImageField
from radaro_utils.serializers.mobile.serializers import RadaroMobileListSerializer, RadaroMobileModelSerializer
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order


class OrderConfirmationPhotoSerializer(NullResultMixin, serializers.Serializer):
    url = RadaroMobileImageField(required=False, allow_null=True, source='image')
    thumbnail_url = RadaroMobileImageField(read_only=True, source='thumb_image_100x100')

    class Meta:
        list_serializer_class = RadaroMobileListSerializer


class SignaturePickUpConfirmationDriverOrderSerializer(NullResultMixin, serializers.ModelSerializer):
    url = RadaroMobileImageField(source='pick_up_confirmation_signature', read_only=True)
    thumbnail_url = RadaroMobileImageField(source='pick_up_confirmation_signature_100x100', read_only=True)

    class Meta:
        model = Order
        fields = ('url', 'thumbnail_url')


class PickUpConfirmationDriverOrderSerializer(NullResultMixin, RadaroMobileModelSerializer):
    photo = OrderConfirmationPhotoSerializer(many=True, source='pick_up_confirmation_photos', read_only=True)
    signature = SignaturePickUpConfirmationDriverOrderSerializer(source='*', read_only=True)

    class Meta:
        model = Order
        fields = ('photo', 'signature', 'comment')
        extra_kwargs = {
            'comment': {'source': 'pick_up_confirmation_comment', 'read_only': True},
        }


class SignaturePreConfirmationDriverOrderSerializer(NullResultMixin, serializers.ModelSerializer):
    url = RadaroMobileImageField(source='pre_confirmation_signature', read_only=True)
    thumbnail_url = RadaroMobileImageField(source='thumb_pre_confirmation_signature_100x100', read_only=True)

    class Meta:
        model = Order
        fields = ('url', 'thumbnail_url')


class PreConfirmationDriverOrderSerializer(NullResultMixin, RadaroMobileModelSerializer):
    photo = OrderConfirmationPhotoSerializer(many=True, source='pre_confirmation_photos', read_only=True)
    signature = SignaturePreConfirmationDriverOrderSerializer(source='*', read_only=True)

    class Meta:
        model = Order
        fields = ('photo', 'signature', 'comment')
        extra_kwargs = {
            'comment': {'source': 'pre_confirmation_comment'},
        }


class SignatureConfirmationDriverOrderSerializer(NullResultMixin, serializers.ModelSerializer):
    url = RadaroMobileImageField(source='confirmation_signature', read_only=True)
    thumbnail_url = RadaroMobileImageField(source='thumb_confirmation_signature_100x100', read_only=True)

    class Meta:
        model = Order
        fields = ('url', 'thumbnail_url')


class OrderConfirmationDocumentSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True)

    class Meta:
        model = OrderConfirmationDocument
        fields = ('id', 'document', 'name', 'tags')
        read_only_fields = ('id',)


class ConfirmationDriverOrderSerializer(NullResultMixin, RadaroMobileModelSerializer):
    photo = OrderConfirmationPhotoSerializer(many=True, source='order_confirmation_photos', read_only=True)
    signature = SignatureConfirmationDriverOrderSerializer(source='*', read_only=True)
    documents = OrderConfirmationDocumentSerializer(source='order_confirmation_documents', many=True, read_only=True)

    class Meta:
        model = Order
        fields = ('photo', 'signature', 'comment', 'documents')
        extra_kwargs = {
            'comment': {'source': 'confirmation_comment'},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        merchant = self.context['request'].user.current_merchant
        if data and not data['documents'] and not merchant.enable_delivery_confirmation_documents:
            del data['documents']
        return data


class StatusByConfirmationValidator:
    instance = None

    def set_context(self, serializer):
        self.instance = getattr(serializer, 'instance', None)

    @staticmethod
    def is_confirmed(order):
        if not order:
            return False
        return any([order.confirmation_signature, order.order_confirmation_photos.exists()])

    def __call__(self, attrs):
        merchant = attrs.get('merchant', self.instance.merchant if self.instance else None)
        if 'status' in attrs and merchant.advanced_completion == merchant.ADVANCED_COMPLETION_REQUIRED:
            status = attrs['status']
            confirmation_required = (
                (status == OrderStatus.WAY_BACK
                 or (status == OrderStatus.DELIVERED and getattr(self.instance, 'status') != OrderStatus.WAY_BACK))
                and merchant.enable_delivery_confirmation
            )
            if confirmation_required and not self.is_confirmed(self.instance):
                raise serializers.ValidationError(
                    {'status': _('You cannot change the status until delivery is confirmed')},
                    code='required_confirmation'
                )


class ConfirmationOrderMixinSerializer(serializers.ModelSerializer):
    pick_up_confirmation = PickUpConfirmationDriverOrderSerializer(read_only=True, source='*')
    pre_confirmation = PreConfirmationDriverOrderSerializer(read_only=True, source='*')
    confirmation = ConfirmationDriverOrderSerializer(read_only=True, source='*')

    class Meta:
        model = Order
        fields = ['pre_confirmation', 'confirmation', 'pick_up_confirmation']
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        merchant = self.context['request'].user.current_merchant
        if not merchant.use_pick_up_status:
            self.fields.pop('pick_up_confirmation', None)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data:
            merchant = self.context['request'].user.current_merchant
            if not merchant.enable_pick_up_confirmation and not data.get('pick_up_confirmation'):
                data.pop('pick_up_confirmation', None)
            if not merchant.enable_delivery_pre_confirmation and not data.get('pre_confirmation'):
                data.pop('pre_confirmation', None)
            if not merchant.enable_delivery_confirmation and not data.get('confirmation'):
                data.pop('confirmation', None)
        return data
