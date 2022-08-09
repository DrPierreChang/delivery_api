from django.conf import settings
from django.db import transaction
from django.dispatch import Signal

from base.utils import dictionaries_difference
from delivery.celery import app

from .models import Event

# Used when the object needs additional asynchronous processing.
# The signal is sent within the Celery task. When using this signal, do not create additional Celery tasks.
trigger_object_post_processing = Signal(providing_args=['event'])

# Used when you need an object that has already been additionally processed.
trigger_object_correlated_operations = Signal(providing_args=['event'])


event_created = Signal(providing_args=['event'])


def create_event(dump_before, dump_after, initiator, instance, sender, track_change_event=None,
                 additional_data_for_event=None, force_create=False, **kwargs):
    key_diff, old_dict, new_dict = dictionaries_difference(dump_before, dump_after)
    if not force_create and not key_diff:
        return
    events = []

    obj_dump = {"old_values": old_dict, "new_values": new_dict}
    events.append(Event.generate_event(
        sender,
        initiator=initiator,
        object=instance,
        event=Event.MODEL_CHANGED,
        obj_dump=obj_dump,
        **kwargs,
    ))

    change_event_diff = set(key_diff).intersection(set(track_change_event or []))
    additional_info_for_fields = {}
    if isinstance(additional_data_for_event, dict) and 'additional_info_for_fields' in additional_data_for_event:
        additional_info_for_fields = additional_data_for_event['additional_info_for_fields']

    for key in change_event_diff:
        obj_dump = additional_info_for_fields.get(key, None)
        events.append(Event.generate_event(
            sender,
            field=str(key),
            new_value=str(new_dict[key])[:255],
            initiator=initiator,
            object=instance,
            event=Event.CHANGED,
            obj_dump=obj_dump,
            **kwargs,
        ))

    send_create_event_signal(events)


def send_create_event_signal(events, **kwargs):
    event_ids = [event.id for event in events if event]
    callback = lambda: _send_create_event_signal.delay(event_ids=event_ids, **kwargs)
    callback() if settings.TESTING_MODE else transaction.on_commit(callback)


@app.task()
def _send_create_event_signal(event_ids, **kwargs):
    events = Event.objects.filter(id__in=event_ids)
    for event in events:
        trigger_object_post_processing.send(Event, event=event, **kwargs)
    for event in events:
        trigger_object_correlated_operations.send(Event, event=event, **kwargs)
