from rest_framework import serializers

from merchant.models import SubBranding


class MerchantSubBrandingSerializer(serializers.ModelSerializer):

    class Meta:
        model = SubBranding
        fields = ('id', 'name', 'logo')
