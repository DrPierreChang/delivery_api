from rest_framework import status
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, UpdateModelMixin
from rest_framework.response import Response

from reporting.model_mapping import serializer_map
from reporting.utils.delete import create_delete_event

from .models import Event
from .signals import create_event, send_create_event_signal


class TrackableCreateModelMixin(CreateModelMixin):
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        Model = serializer.instance.__class__
        serializer_class = serializer_map.get_for(Model)
        if serializer_class:
            dump = serializer_class(serializer.instance).data
        else:
            dump = serializer.data
        dump.update({
            'str_repr': str(serializer.instance),
            'content_type': Model.__name__.lower()
        })
        event = Event.generate_event(self, initiator=request.user,
                                     object=serializer.instance,
                                     obj_dump=dump,
                                     event=Event.CREATED)
        send_create_event_signal(events=[event])
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class TrackableUpdateModelMixin(UpdateModelMixin):
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        DeltaSerializer = serializer_map.get_for(instance.__class__)
        old_dict = DeltaSerializer(instance).data
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        instance.refresh_from_db()
        new_dict = DeltaSerializer(instance).data
        create_event(old_dict, new_dict, initiator=request.user, instance=instance, sender=self,
                     track_change_event=DeltaSerializer.Meta.track_change_event)

        return Response(self.get_serializer(instance).data)


class TrackableDestroyModelMixin(DestroyModelMixin):
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        create_delete_event(self, obj, request.user, request)
        self.perform_destroy(obj)
        return Response(status=status.HTTP_204_NO_CONTENT)
