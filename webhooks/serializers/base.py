from rest_framework import serializers

from webhooks.models import MerchantAPIKey


class APIKeySerializer(serializers.ModelSerializer):
    merchant = serializers.SerializerMethodField()

    def get_merchant(self, instance):
        return instance.creator.current_merchant_id

    class Meta:
        model = MerchantAPIKey
        fields = ('key', 'created', 'merchant', 'available', 'name', 'is_master_key')
        read_only_fields = ('created', 'merchant', 'key')


__all__ = ['APIKeySerializer']
