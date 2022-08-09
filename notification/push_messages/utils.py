from base.models import Member

from .event_composers import EventMessage


def send_on_event_data_notifications(merchant, obj_preview, event):
    message = EventMessage(obj_preview, event)
    drivers = merchant.member_set.filter(role__in=[Member.DRIVER, Member.MANAGER_OR_DRIVER])
    for driver in drivers:
        driver.send_versioned_push(message, background=True)
