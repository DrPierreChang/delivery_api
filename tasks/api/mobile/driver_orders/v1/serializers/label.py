from rest_framework import serializers

from merchant.api.legacy.serializers.fields import LabelHexColorField
from merchant.models import Label
from radaro_utils.serializers.mobile.serializers import RadaroMobileListSerializer


class LabelSerializer(serializers.ModelSerializer):
    color = LabelHexColorField(required=False)

    class Meta:
        list_serializer_class = RadaroMobileListSerializer
        model = Label
        exclude = ('merchant',)
        read_only_fields = ('merchant',)
