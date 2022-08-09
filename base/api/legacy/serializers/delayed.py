from __future__ import unicode_literals

from rest_framework import serializers

from base.models import SampleFile


class DelayedTaskBaseSerializer(serializers.ModelSerializer):
    log = serializers.JSONField(read_only=True)

    class Meta:
        fields = ('id', 'status', 'log',)
        read_only_fields = ('id', 'status')


class DelayedTaskSerializer(serializers.ModelSerializer):
    log = serializers.JSONField(read_only=True)

    class Meta:
        fields = ('id', 'status', 'log',)
        read_only_fields = ('id', 'status')


class SampleFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SampleFile
        exclude = []
