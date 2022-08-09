from rest_framework.generics import get_object_or_404

from reporting.model_mapping import serializer_map
from reporting.signals import create_event


class track_fields_on_change(object):
    def __init__(self, instances, should_track=True, initiator=None, sender=None, **kwargs):
        self.sender = sender
        self.initiator = initiator
        self.should_track = should_track
        self.instances = instances if isinstance(instances, (list, tuple)) else [instances]
        if self.instances:
            self.model = type(self.instances[0])
            self.delta_serializer = serializer_map.get_for(self.model)
        else:
            self.model = None
        self.event_kwargs = kwargs

    def __enter__(self):
        if self.model is None:
            return self

        if self.should_track:
            ids = [inst.id for inst in self.instances]
            if None in ids:
                raise self.model.DoesNotExist()
            old_objs = self.model.objects.filter(id__in=ids)
            self.old_dict = {obj.id: self.delta_serializer(obj).data for obj in old_objs}
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.model is None:
            return

        if exc_type is None and self.should_track:
            for instance in self.instances:
                if instance.id not in self.old_dict:
                    continue
                instance.refresh_from_db()
                new_dict = self.delta_serializer(instance).data
                create_event(
                    self.old_dict[instance.id],
                    new_dict,
                    initiator=self.initiator,
                    instance=instance,
                    sender=self.sender,
                    track_change_event=self.delta_serializer.Meta.track_change_event,
                    **self.event_kwargs,
                )


class track_fields_for_offline_changes(object):
    event_kwargs = None

    def __init__(self, instance, sender, request, offline_happened_at=None):
        self.instance = instance
        self.sender = sender
        self.request = request

        self.event_kwargs = {'instance': None}
        if offline_happened_at:
            self.event_kwargs['happened_at'] = offline_happened_at

    def __enter__(self):
        self.delta_serializer = serializer_map.get_for(self.instance.__class__)
        self.old_dict = self.delta_serializer(self.instance, context={'request': self.request}).data
        return self.event_kwargs

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            raise
        instance = self.event_kwargs.pop('instance') or get_object_or_404(self.instance.__class__, id=self.instance.id)

        new_dict = self.delta_serializer(instance, context={'request': self.request}).data
        create_event(
            self.old_dict,
            new_dict,
            initiator=self.request.user if not self.request.user.is_anonymous else None,
            instance=instance,
            sender=self.sender,
            track_change_event=self.delta_serializer.Meta.track_change_event,
            **self.event_kwargs,
        )
