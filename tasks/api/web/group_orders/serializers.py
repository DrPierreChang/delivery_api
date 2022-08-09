from rest_framework import serializers

from ..subbrand_orders.serializers import ListSubManagerOrderSerializer


class ListGroupOrderSerializer(ListSubManagerOrderSerializer):
    merchant = serializers.CharField()
    sub_branding = serializers.CharField()

    class Meta(ListSubManagerOrderSerializer.Meta):
        fields = ListSubManagerOrderSerializer.Meta.fields + ('merchant', 'sub_branding')
