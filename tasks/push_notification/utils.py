from __future__ import absolute_import

import itertools
from collections import namedtuple

from tasks.mixins.order_status import OrderStatus

from .push_messages.order_change_status_composers import (
    AssignedMessage,
    BulkAssignedMessage,
    BulkUnassignedMessage,
    DefaultStatusMessage,
    InProgressMessage,
    UnassignedMessage,
)

FakeEvent = namedtuple('FakeEvent', 'object')


def select_notification_for_order_with_driver(order, new_values, old_values, event):
    driver, msg = order.driver, None
    new_status = new_values['status']
    old_status = old_values.get('status', '')
    if new_status == OrderStatus.ASSIGNED:
        msg = AssignedMessage(driver=driver, order=order, initiator=event.initiator)
    # If driver completes order by himself he doesn't need push, except it was finished by geofence
    elif (order.is_completed_by_geofence and event.is_online) or event.initiator_id != order.driver_id:
        completed_by_manager = event.initiator_id == order.manager_id
        if new_status == OrderStatus.IN_PROGRESS:
            msg = InProgressMessage(driver=driver, order=order, initiator=event.initiator)
        elif new_status == OrderStatus.PICK_UP:
            msg = DefaultStatusMessage(new_status, driver=driver, order=order, initiator=event.initiator)
        elif new_status in (OrderStatus.FAILED, OrderStatus.DELIVERED, OrderStatus.WAY_BACK) and \
                (old_status != OrderStatus.WAY_BACK or completed_by_manager):
            msg = DefaultStatusMessage(new_status, driver=driver, order=order, initiator=event.initiator)
    return [(driver, msg), ]


def select_unassign_notification(order, new_values, old_values, event, background_notification):
    from base.models import Member

    driver, msg = None, None
    initiator_not_driver = event.initiator and not event.initiator.is_driver
    status_changed_to_unassigned = old_values['status'] != new_values['status'] == OrderStatus.NOT_ASSIGNED
    if status_changed_to_unassigned and (background_notification or initiator_not_driver):
        driver = Member.all_drivers.all().not_deleted().get(id=old_values['driver'])
        msg = UnassignedMessage(driver=driver, order=order)
    return [(driver, msg), ]


def select_notifications_on_reassign(order, new_values, old_values, event):
    from base.models import Member

    old_driver = Member.drivers.get(id=old_values['driver'])
    unassign_msg = UnassignedMessage(driver=old_driver, order=order)
    new_driver = Member.drivers.get(id=new_values['driver'])
    assign_msg = AssignedMessage(driver=new_driver, order=order, initiator=event.initiator)
    return [(old_driver, unassign_msg), (new_driver, assign_msg), ]


def create_and_send_job_status_notification(order, new_values, old_values, event, background_notification=False):
    notifications = []

    if old_values.get('driver') is not None and new_values.get('driver') is not None \
            and old_values.get('driver') != new_values.get('driver'):
        notifications = select_notifications_on_reassign(order, new_values, old_values, event)

    elif all([order.driver, 'status' in new_values]) and order.driver.push_available():
        notifications = select_notification_for_order_with_driver(order, new_values, old_values, event)

    elif 'status' in old_values and 'status' in new_values and 'driver' in new_values:
        notifications = select_unassign_notification(
            order, new_values, old_values,
            event, background_notification
        )

    for (driver, msg) in notifications:
        if msg:
            driver.send_versioned_push(msg, background=background_notification)


class BaseBulkStatusChangeHandler(object):

    def __init__(self, background_notification=False):
        self.background_notification = background_notification

    def send_notifications(self, events):
        for _driver_id, _events in itertools.groupby(events, self._driver_id_getter):
            events = list(sorted(_events, key=lambda x: x.object.order_id))
            count = len(events)
            if count == 1:
                handle_single_status_notification(events[0], self.background_notification)
            else:
                self._send_bulk(_driver_id, events)

    def _driver_id_getter(self, event):
        raise NotImplementedError()

    def _send_bulk(self, driver_id, events):
        raise NotImplementedError()


class BulkAssignEventsHandler(BaseBulkStatusChangeHandler):
    def _driver_id_getter(self, event):
        return event.object.driver_id

    def _send_bulk(self, driver_id, events):
        driver = events[0].object.driver
        msg = BulkAssignedMessage(driver=driver, events=events)
        driver.send_versioned_push(msg, background=self.background_notification)


class BulkUnassignEventsHandler(BaseBulkStatusChangeHandler):
    def _driver_id_getter(self, event):
        return event.obj_dump['old_values']['driver']

    def _send_bulk(self, driver_id, events):
        from base.models import Member
        driver = Member.drivers.get(id=driver_id)
        msg = BulkUnassignedMessage(driver=driver, events=events)
        driver.send_versioned_push(msg, background=self.background_notification)


class BulkReassignEventsHandler(BaseBulkStatusChangeHandler):
    def _driver_id_getter(self, event):
        return event.object.driver_id, event.obj_dump['old_values']['driver']

    def _send_bulk(self, driver_ids, events):
        from base.models import Member
        assigned_driver_id, unassigned_driver_id = driver_ids
        assigned_driver = events[0].object.driver
        msg = BulkAssignedMessage(driver=assigned_driver, events=events)
        assigned_driver.send_versioned_push(msg, background=self.background_notification)
        unassigned_driver = Member.drivers.get(id=unassigned_driver_id)
        msg = BulkUnassignedMessage(driver=unassigned_driver, events=events)
        unassigned_driver.send_versioned_push(msg, background=self.background_notification)


def handle_single_status_notification(event_obj, background_notification=False):
    from reporting.models import Event
    new_values, old_values = None, {}
    if event_obj.event == Event.CREATED:
        new_values = event_obj.obj_dump
    elif event_obj.event == Event.MODEL_CHANGED:
        new_values = (event_obj.obj_dump or {}).get('new_values', {})
        old_values = (event_obj.obj_dump or {}).get('old_values', {})
    if new_values is not None:
        create_and_send_job_status_notification(
            order=event_obj.object, new_values=new_values,
            old_values=old_values, event=event_obj,
            background_notification=background_notification
        )


def send_notifications_for_assigned_jobs_by_bulk(drivers):
    for driver, _orders in drivers:
        events = [FakeEvent(o) for o in _orders]
        if len(events) == 1:
            o = events[0].object
            msg = AssignedMessage(driver=driver, order=o, initiator=o.manager)
        else:
            msg = BulkAssignedMessage(driver=driver, events=events)
        driver.send_versioned_push(msg)
