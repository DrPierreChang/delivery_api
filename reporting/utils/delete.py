from django.contrib.contenttypes.models import ContentType

from crequest.middleware import CrequestMiddleware

from reporting.model_mapping import serializer_map
from reporting.models import Event
from reporting.signals import send_create_event_signal


def create_delete_event(sender, obj, initiator, request=None, merchant=None):
    request = request or CrequestMiddleware.get_request()

    Model = type(obj)
    DeltaSerializer = serializer_map.get_for(Model)
    dump = DeltaSerializer(obj).data
    detailed_dumps = serializer_map.serialize_detailed_for_all_versions(obj, {'request': request})

    dump.update({
        'id': obj.id,
        'str_repr': str(obj),
        'content_type': ContentType.objects.get_for_model(Model, for_concrete_model=False),
    })
    if merchant:
        dump['merchant_id'] = merchant.id

    event = Event.generate_event(sender,
                                 initiator=initiator,
                                 object=dump,
                                 event=Event.DELETED,
                                 detailed_dump=detailed_dumps)
    send_create_event_signal(events=[event])
