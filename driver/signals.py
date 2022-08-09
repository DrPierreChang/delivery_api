# Handler for logout event
from django.db.models.signals import post_save
from django.dispatch import receiver

from base import signal_senders
from base.models import Member
from base.signals import logout_event
from driver.api.legacy.serializers.driver import DriverStatusSerializer
from driver.utils import WorkStatus
from notification.push_messages.event_composers import EventMessage
from reporting.models import Event
from reporting.signals import send_create_event_signal


@receiver(logout_event, sender=signal_senders.senders[Member.DRIVER])
def set_driver_offline(sender, **kwargs):
    user = kwargs['user']
    if user.work_status != WorkStatus.NOT_WORKING:
        old_work_status = user.work_status
        user.set_availability_status(WorkStatus.NOT_WORKING)
        events = []

        events.append(Event.generate_event(
            set_driver_offline,
            initiator=user,
            object=user,
            event=Event.MODEL_CHANGED,
            obj_dump={
                'old_values': {'work_status': old_work_status},
                'new_values': {'work_status': WorkStatus.NOT_WORKING}
            }
        ))

        work_status_obj_dump = None
        if user.last_location:
            work_status_obj_dump = DriverStatusSerializer.get_location_data_for_work_status(user.last_location.location)

        events.append(Event.generate_event(
            set_driver_offline,
            initiator=user,
            field='work_status',
            new_value=WorkStatus.NOT_WORKING,
            object=user,
            event=Event.CHANGED,
            obj_dump=work_status_obj_dump,
        ))

        send_create_event_signal(events=events)


@receiver(post_save, sender=Event)
def check_driver_update(sender, instance, **kwargs):
    if not type(instance.object) == Member:
        return
    if not instance.event == Event.MODEL_CHANGED:
        return
    if not instance.object.is_driver:
        return
    if instance.object_id == instance.initiator_id:
        return

    # A different push is used for these fields
    ignored_fields = {'is_offline_forced', 'is_online', 'work_status', 'status', 'last_ping', 'has_internet_connection'}
    changed_fields = set(instance.obj_dump['old_values'].keys())
    if not (changed_fields - ignored_fields):
        return

    driver = instance.object
    driver_preview = {
        'id': driver.id,
        'model': Member.__name__
    }
    msg = EventMessage(driver_preview, EventMessage.MODEL_CHANGED)
    driver.send_versioned_push(msg, background=True)


__all__ = ['set_driver_offline', 'check_driver_update']
