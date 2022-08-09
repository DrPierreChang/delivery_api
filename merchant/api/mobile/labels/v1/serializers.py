from rest_framework import serializers

from merchant.api.legacy.serializers.fields import LabelHexColorField
from merchant.models import Label


class MerchantLabelSerializer(serializers.ModelSerializer):
    color = LabelHexColorField()

    class Meta:
        model = Label
        fields = ('id', 'color', 'name')
