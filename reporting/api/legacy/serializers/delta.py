from rest_framework import serializers


class DeltaSerializer(serializers.ModelSerializer):
    class Meta:
        fields = '__all__'
        track_change_event = []
