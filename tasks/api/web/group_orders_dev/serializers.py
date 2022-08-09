from rest_framework import serializers

from ..subbrand_orders_dev.serializers import ShortSubManagerOrderSerializer


class ShortGroupSubManagerOrderSerializer(ShortSubManagerOrderSerializer):
    merchant = serializers.CharField()
    sub_branding = serializers.CharField()

    class Meta(ShortSubManagerOrderSerializer.Meta):
        fields = ShortSubManagerOrderSerializer.Meta.fields + ('merchant', 'sub_branding')
