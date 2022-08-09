from django.contrib.contenttypes.models import ContentType

from rest_framework import serializers

from base.api.legacy.serializers import SmallUserInfoSerializer
from reporting.model_mapping import serializer_map
from reporting.models import Event
from tasks.models import ConcatenatedOrder, Order


class WebEventSerializer(serializers.ModelSerializer):
    VERSION = 'web'

    event = serializers.CharField(source='get_event_display')
    initiator = SmallUserInfoSerializer()
    obj_dump = serializers.SerializerMethodField()
    content_type = serializers.SerializerMethodField()
    object = serializers.SerializerMethodField()

    def get_content_type(self, instance):
        content_type = instance.get_content_type_model()

        # On the web, the concatenated order and order are considered the same type
        if content_type == ContentType.objects.get_for_model(ConcatenatedOrder, for_concrete_model=False).model:
            return ContentType.objects.get_for_model(Order).model
        return content_type

    def get_object(self, instance):
        if instance.event in [Event.MODEL_CHANGED, Event.CREATED]:
            serializer = serializer_map.get_for_detailed_dump(type(instance.object), version=self.VERSION)
            return serializer(instance.object, context=self.context).data
        elif instance.event == Event.DELETED:
            return self.get_detailed_dump(instance)
        return None

    def get_detailed_dump(self, instance):
        if not instance.detailed_dump:
            return None
        else:
            return instance.detailed_dump.get(self.VERSION, instance.detailed_dump)

    def get_obj_dump(self, instance):
        if instance.event in [Event.CREATED, Event.DELETED]:
            return {}

        dump = instance.obj_dump
        converter = serializer_map.get_converter_for_obj_dump(type(instance.object), self.VERSION)
        if converter is None:
            return dump

        if instance.event == Event.MODEL_CHANGED:
            class Serializer(serializers.Serializer):
                old_values = converter()
                new_values = converter()
            return Serializer(dump).data

        return dump

    class Meta:
        fields = ('event', 'obj_dump', 'initiator', 'content_type', 'object_id', 'object')
        model = Event


__all__ = ['WebEventSerializer']
