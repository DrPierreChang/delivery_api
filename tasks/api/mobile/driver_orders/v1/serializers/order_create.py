from django.db import transaction
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from radaro_utils.serializers.validators import LaterThenNowValidator
from tasks.models.orders import order_deadline

from .barcodes import BarcodeSerializer
from .order import DriverOrderSerializer


class DriverOrderCreateSerializer(DriverOrderSerializer):
    barcodes = BarcodeSerializer(many=True, required=False)

    class Meta(DriverOrderSerializer.Meta):
        editable_fields = {
            'title', 'driver_id', 'customer', 'pickup', 'deliver_address', 'pickup_address',
            'pickup_after', 'pickup_before', 'deliver_after', 'deliver_before',
            'comment', 'barcodes', 'label_ids', 'skill_set_ids', 'sub_branding_id',
        }
        read_only_fields = list(set(DriverOrderSerializer.Meta.fields) - set(editable_fields))
        extra_kwargs = {
            'deliver_before': {'default': order_deadline, 'validators': [LaterThenNowValidator()]},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if bool(attrs.get('pickup_address')) != bool(attrs.get('pickup')):
            raise serializers.ValidationError(
                _('Pickup customer and pickup address must be used together'), code='invalid_pickup'
            )
        if not attrs.get('pickup_address'):
            attrs.pop('pickup_after', None)
            attrs.pop('pickup_before', None)

        return attrs

    def create(self, validated_data):
        barcodes = validated_data.pop('barcodes', [])
        labels = validated_data.pop('labels', [])
        skill_sets = validated_data.pop('skill_sets', [])

        with transaction.atomic():
            validated_data['customer'] = self.fields['customer'].create(validated_data['customer'])
            if 'pickup' in validated_data:
                pickup_customer = self.fields['pickup']
                validated_data['pickup'] = pickup_customer.create(validated_data['pickup'])
            if 'deliver_address' in validated_data:
                deliver = self.fields['deliver_address']
                validated_data['deliver_address'] = deliver.create(validated_data['deliver_address'])
            if 'pickup_address' in validated_data:
                pickup = self.fields['pickup_address']
                validated_data['pickup_address'] = pickup.create(validated_data['pickup_address'])

            order = super().create(validated_data)
            if barcodes:
                self.fields['barcodes'].create(map(lambda barcode: {'order': order, **barcode}, barcodes))
            if labels:
                order.labels.add(*labels)
            if skill_sets:
                order.skill_sets.add(*skill_sets)

        return order
