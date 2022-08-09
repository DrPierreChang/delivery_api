from rest_framework import serializers

from merchant.api.web.hubs.serializers import WebHubSerializer
from tasks.models import Order

from ..location import WebLocationSerializer


class WaybackWebOrderSerializer(serializers.ModelSerializer):
    point = WebLocationSerializer(source='wayback_point', allow_null=True)
    hub = WebHubSerializer(source='wayback_hub', allow_null=True)

    class Meta:
        model = Order
        fields = ('point', 'hub')
