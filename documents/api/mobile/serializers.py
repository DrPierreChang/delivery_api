from rest_framework import serializers

from documents.models import Tag
from radaro_utils.serializers.mobile.serializers import RadaroMobileListSerializer
from reporting.model_mapping import serializer_map


@serializer_map.register_serializer
class TagSerializer(serializers.ModelSerializer):
    class Meta:
        list_serializer_class = RadaroMobileListSerializer
        model = Tag
        fields = ('id', 'name')
        read_only_fields = ('id',)
        track_change_event = ('name',)
