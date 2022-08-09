from reporting.model_mapping import serializer_map
from reporting.models import Event
from reporting.signals import send_create_event_signal


def create_create_event(sender, obj, initiator):
    Model = type(obj)
    DeltaSerializer = serializer_map.get_for(Model)
    dump = DeltaSerializer(obj).data

    dump.update({
        'str_repr': str(obj),
        'content_type': Model.__name__.lower(),
    })
    event = Event.generate_event(sender,
                                 initiator=initiator,
                                 object=obj,
                                 obj_dump=dump,
                                 event=Event.CREATED)
    send_create_event_signal(events=[event])
