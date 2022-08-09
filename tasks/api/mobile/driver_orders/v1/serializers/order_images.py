from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from radaro_utils.serializers.mobile.fields import ImageListField, RadaroMobileImageField
from tasks.api.legacy.serializers.mixins import UnpackOrderPhotosMixin
from tasks.models import Order, OrderConfirmationPhoto, OrderPickUpConfirmationPhoto, OrderPreConfirmationPhoto

from .order import OfflineOrderMixinSerializer


class ImageOrderSerializer(UnpackOrderPhotosMixin, OfflineOrderMixinSerializer, serializers.ModelSerializer):
    pre_confirmation_signature = RadaroMobileImageField(required=False, allow_null=True)
    pre_confirmation_photos = ImageListField(required=False, default=[])

    confirmation_signature = RadaroMobileImageField(required=False, allow_null=True)
    confirmation_photos = ImageListField(required=False, default=[], source='order_confirmation_photos')

    pick_up_confirmation_signature = RadaroMobileImageField(required=False, allow_null=True)
    pick_up_confirmation_photos = ImageListField(required=False, default=[])

    confirmation_photos_list = [('pre_confirmation_photos', OrderPreConfirmationPhoto),
                                ('order_confirmation_photos', OrderConfirmationPhoto),
                                ('pick_up_confirmation_photos', OrderPickUpConfirmationPhoto)]

    class Meta:
        model = Order
        pickup_confirmation_fields = ('pick_up_confirmation_signature', 'pick_up_confirmation_photos',
                                      'pick_up_confirmation_comment')
        pre_confirmation_fields = ('pre_confirmation_signature', 'pre_confirmation_photos', 'pre_confirmation_comment')
        confirmation_fields = ('confirmation_signature', 'confirmation_photos', 'confirmation_comment')
        fields = pickup_confirmation_fields + pre_confirmation_fields + confirmation_fields + ('offline_happened_at',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        merchant = kwargs['context']['request'].user.current_merchant

        if not merchant.enable_delivery_pre_confirmation:
            for field in self.Meta.pre_confirmation_fields:
                self.fields.pop(field)

        if not merchant.enable_delivery_confirmation:
            for field in self.Meta.confirmation_fields:
                self.fields.pop(field)

        if not merchant.enable_pick_up_confirmation:
            for field in self.Meta.pickup_confirmation_fields:
                self.fields.pop(field)

    def validate(self, attrs):
        if self.instance.status in [Order.NOT_ASSIGNED]:
            # The mobile application first sends a confirmation, then changes the status.
            # Therefore, the validation by status is done in this way.
            if any(attrs.get(attr) for attr in self.Meta.pickup_confirmation_fields):
                raise serializers.ValidationError(
                    _('You are not able to send pick up confirmation with the current status'),
                    code='invalid_status_for_pick_up_confirmation'
                )

            if any(attrs.get(attr) for attr in self.Meta.pre_confirmation_fields):
                raise serializers.ValidationError(
                    _('You are not able to send confirmation with the current status'),
                    code='invalid_status_for_pre_confirmation'
                )

            if any(attrs.get(attr) for attr in self.Meta.confirmation_fields + ('order_confirmation_photos',)):
                raise serializers.ValidationError(
                    _('You are not able to send confirmation with the current status'),
                    code='invalid_status_for_confirmation'
                )

        return super().validate(attrs)

    def update(self, instance, validated_data):
        order = super().update(instance, validated_data)
        if validated_data.get('confirmation_signature') or validated_data.get('confirmation_photos'):
            order.handle_confirmation()
        return order
