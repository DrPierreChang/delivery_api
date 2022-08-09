from rest_framework import serializers

from .models import RevelSystem


class RevelSystemSerializer(serializers.ModelSerializer):
    class Meta:
        model = RevelSystem
        fields = ('subdomain', 'merchant', 'api_key', 'api_secret')

    def create(self, validated_data):
        user = self.context['request'].user
        return super(RevelSystemSerializer, self).create(dict(validated_data, creator=user))
