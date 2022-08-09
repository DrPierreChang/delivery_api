from django.conf import settings

from rest_framework import serializers


class RadaroRouterUserSerializer(serializers.Serializer):
    server_name = serializers.CharField(default=settings.CURRENT_HOST, max_length=256)
    cluster_number = serializers.CharField(default=settings.CLUSTER_NUMBER.lower(), max_length=4)
    email = serializers.EmailField(required=True)
    phone = serializers.CharField(required=True, max_length=40)
    username = serializers.CharField(required=True, max_length=256)
    external_pk = serializers.IntegerField(source='id')


class RadaroRouterInviteSerializer(serializers.Serializer):
    server_name = serializers.CharField(default=settings.CURRENT_HOST, max_length=256)
    email = serializers.EmailField(required=True)
    phone = serializers.CharField(required=True, max_length=40)
    external_pk = serializers.IntegerField(source='id')
