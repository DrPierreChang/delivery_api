from django.db import models

import sentry_sdk

from notification.models.mixins import SendNotificationMixin
from routing.google import GoogleClient
from tasks.descriptors import OrderStatusesEventsDescriptor
from tasks.mixins.order_status import OrderStatus


class OrderSendNotificationMixin(SendNotificationMixin):

    def _get_sender(self):
        sender = super(OrderSendNotificationMixin, self)._get_sender()

        return self.merchant.sms_sender or sender


class TerminateCodeSendNotification(SendNotificationMixin):

    def _get_email(self):
        email = super(TerminateCodeSendNotification, self)._get_email()

        return self.email_notification_recipient or email


class OrderTimeDistanceMixin(models.Model):
    duration = models.DurationField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)

    status_events = OrderStatusesEventsDescriptor()

    order_distance = models.PositiveIntegerField(null=True, blank=True)
    pick_up_distance = models.PositiveIntegerField(null=True, blank=True)
    wayback_distance = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        abstract = True

    def _calculate_distances(self, points):
        try:
            with GoogleClient.track_merchant(self.merchant):
                return GoogleClient().directions_distance(points[0], *points[1:], track_merchant=True)
        except Exception as ex:
            sentry_sdk.capture_exception(ex)

    def _pre_calculate_order_distance(self, points, to_status):
        distances = self._calculate_distances(points)
        if distances is not None:
            if to_status == OrderStatus.PICK_UP:
                self.pick_up_distance = distances[0]
            self.order_distance = sum(distances)

    def _pre_calculate_wayback_distance(self, points):
        initial_wayback_distance = self.wayback_distance or 0
        if points is None:
            self.order_distance -= initial_wayback_distance
            self.wayback_distance = 0
            self.save(update_fields=['wayback_distance', 'order_distance'])
            return
        distances = self._calculate_distances(points)
        if distances is not None:
            self.wayback_distance = distances[0]
            self.order_distance += (self.wayback_distance - initial_wayback_distance)
            self.save(update_fields=['wayback_distance', 'order_distance'])

    @property
    def picked_up_at(self):
        pick_up_event, picked_up_event = self.status_events[OrderStatus.PICK_UP],\
                                         self.status_events[OrderStatus.PICKED_UP]
        if picked_up_event:
            return picked_up_event.happened_at
        return self.in_progress_at if pick_up_event else None

    @property
    def in_progress_at(self):
        in_progress_event = self.status_events[OrderStatus.IN_PROGRESS]
        return in_progress_event.happened_at if in_progress_event else None

    @property
    def assigned_at(self):
        if self.status == OrderStatus.NOT_ASSIGNED:
            return
        assign_event = self.status_events.get_assign_event()
        return assign_event.happened_at if assign_event else None

    @property
    def finished_at(self):
        finish_event = self.status_events[OrderStatus.status_groups.FINISHED]
        return finish_event.happened_at if finish_event else None

    @property
    def wayback_at(self):
        wayback_event = self.status_events[OrderStatus.WAY_BACK]
        return wayback_event.happened_at if wayback_event else None

    @property
    def statuses_time_distance(self):
        from tasks.utils.status_time_distances import time_distance_calculators

        pick_up_start, picked_up_start = None, None
        in_progress_start = self.in_progress_at
        wayback_start = self.wayback_at
        if self.status_events[OrderStatus.PICK_UP]:
            pick_up_start = self.started_at
        if self.status_events[OrderStatus.PICKED_UP]:
            picked_up_start = self.picked_up_at
        arguments = [self, pick_up_start, picked_up_start, in_progress_start, wayback_start]

        result_dict = {}
        for calculator in time_distance_calculators:
            result_dict[calculator.status_name] = None
            if calculator.exists(*arguments):
                _time, _distance = calculator.calc(*arguments)
                result_dict[calculator.status_name] = {'time': calculator.format_timedelta_seconds(_time),
                                                       'distance': _distance}
        return result_dict
