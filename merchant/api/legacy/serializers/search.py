from rest_framework import serializers

from driver.api.legacy.serializers.driver import ListDriverSerializer, ListDriverSerializerV2
from tasks.api.legacy.serializers.core import OrderLocationSerializer, OrderLocationSerializerV2
from tasks.api.legacy.serializers.orders import OrderSerializer, OrderSerializerV2

SEARCH_CLASSES = {
    'default': {
        'Member': ListDriverSerializer,
        'Order': OrderSerializer,
        'OrderLocation': OrderLocationSerializer
    },
    2: {
        'Member': ListDriverSerializerV2,
        'Order': OrderSerializerV2,
        'OrderLocation': OrderLocationSerializerV2
    }
}


class SearchSerializer(serializers.Serializer):

    def to_representation(self, instance):
        object_class = instance.object.__class__.__name__
        serializer_version = SEARCH_CLASSES.get(self.context['request'].version, SEARCH_CLASSES['default'])
        object_serializer_class = serializer_version.get(object_class)
        if object_serializer_class:
            data = object_serializer_class(instance=instance.object, context=self.context).data
            data.update({'obj_type': object_class})
            return data
