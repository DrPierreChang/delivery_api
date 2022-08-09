from __future__ import absolute_import, unicode_literals

from django.utils.translation import ugettext_lazy as _

from notification.push_messages.composers import TypedTextPushMessage
from notification.push_messages.mixins import AppealingMessageMixin
from tasks.mixins.order_status import OrderStatus

from .mixins import VersionedOrderMessageMixin


# {appeal()}, (|{message} ){job_prefix} "{job_name()}"(.|{postfix()})
class OrderStatusChangeMessage(VersionedOrderMessageMixin, AppealingMessageMixin, TypedTextPushMessage):
    message = None
    message_type = 'JOB_{}'
    job_prefix = None
    _status = None

    def __init__(self, driver, *args, **kwargs):
        self.driver = driver
        super(OrderStatusChangeMessage, self).__init__(*args, **kwargs)

    @property
    def status(self):
        return OrderStatus._status_dict[self._status].title()

    def _get_appeal(self, driver, *args, **kwargs):
        return driver.first_name

    def _get_message_part(self, message, *args, **kwargs):
        msg = '' if message is None else '{} '.format(message)
        return '{}{}'.format(msg, self._get_job(*args, **kwargs))

    def _get_job_name(self, *args, **kwargs):
        raise NotImplementedError()

    def _get_job(self, *args, **kwargs):
        return '{} \"{}\"'.format(self.job_prefix, self._get_job_name(*args, **kwargs))

    def get_message(self, *args, **kwargs):
        message = super(OrderStatusChangeMessage, self).get_message(
            message=self.message, driver=self.driver, order=self.order, *args, **kwargs
        )
        return message

    def get_message_type(self, *args, **kwargs):
        return self.message_type.format(self._status.upper())


# {appeal()}, (your current job|{job_prefix}) "{job_name()}" (has been|{action}) (|{destination}){initiator}.
class OrderStatusChangeMessageWithAuthor(OrderStatusChangeMessage):
    destination = ''
    job_prefix = _('your current job')
    action = _('has been')

    def __init__(self, initiator, *args, **kwargs):
        self.initiator = initiator
        super(OrderStatusChangeMessageWithAuthor, self).__init__(*args, **kwargs)

    def _get_destination(self, *args, **kwargs):
        return self.destination

    def _get_initiator(self, *args, **kwargs):
        by_manager = self.initiator and self.initiator.id == self.order.manager_id
        return _(' by the manager') if by_manager else ''

    def _get_postfix(self, *args, **kwargs):
        return ' {} {}{}'.format(self.action,
                                 self._get_destination(*args, **kwargs),
                                 self._get_initiator(*args, **kwargs))


class DefaultStatusMessage(OrderStatusChangeMessageWithAuthor):
    destination = _('marked as')

    def __init__(self, status, *args, **kwargs):
        self._status = status
        super(DefaultStatusMessage, self).__init__(*args, **kwargs)

    def _get_destination(self, *args, **kwargs):
        return '{} \"{}\"'.format(self.destination, self.status)

    def _get_job_name(self, *args, **kwargs):
        return self.order.title


class AvailableMessage(OrderStatusChangeMessage):
    _status = OrderStatus.NOT_ASSIGNED
    job_prefix = _('Job')
    message_type = 'JOB_AVAILABLE'

    def _get_job_name(self, *args, **kwargs):
        return self.order.title

    def _get_postfix(self, *args, **kwargs):
        return _(' is available')

    def get_message_type(self, *args, **kwargs):
        return self.message_type


class NotAvailableMessage(OrderStatusChangeMessage):
    _status = OrderStatus.NOT_ASSIGNED
    job_prefix = 'Job'
    message_type = 'JOB_NOT_AVAILABLE'

    def _get_job_name(self, *args, **kwargs):
        return self.order.title

    def _get_postfix(self, *args, **kwargs):
        return ' is not available'

    def get_message_type(self, *args, **kwargs):
        return self.message_type


class UnassignedMessage(OrderStatusChangeMessage):
    _status = OrderStatus.NOT_ASSIGNED
    job_prefix = _('Job')
    message_type = 'JOB_UNASSIGNED'

    def _get_job_name(self, *args, **kwargs):
        return self.order.title

    def _get_postfix(self, *args, **kwargs):
        return _(' was unassigned from you')

    def get_message_type(self, *args, **kwargs):
        return self.message_type


class AssignedMessage(OrderStatusChangeMessage):
    _status = OrderStatus.ASSIGNED
    message = _("you have received")
    job_prefix = _('a new job:')

    def _get_job_name(self, *args, **kwargs):
        return self.order.deliver_address.address

    def _get_postfix(self, *args, **kwargs):
        return ''


class InProgressMessage(DefaultStatusMessage):

    def __init__(self, *args, **kwargs):
        super(InProgressMessage, self).__init__(status=OrderStatus.IN_PROGRESS, *args, **kwargs)


class BulkAssignedMessage(AppealingMessageMixin, TypedTextPushMessage):
    message_type = 'BULK_JOBS_ASSIGNED'
    message = _("you've received")

    def __init__(self, driver, events, *args, **kwargs):
        self.events = events
        self.driver = driver
        super(BulkAssignedMessage, self).__init__(*args, **kwargs)

    def _get_appeal(self, *args, **kwargs):
        return self.driver.first_name

    def _get_postfix(self, *args, **kwargs):
        return _(' {count} new jobs').format(count=len(self.events))

    def get_kwargs(self, version=1, *args, **kwargs):
        kw = super(BulkAssignedMessage, self).get_kwargs(version, *args, **kwargs)
        if version == 1:
            kw['data']['orders_ids'] = [o.object.order_id for o in self.events]
        else:
            kw['data']['server_entity_ids'] = [o.object.id for o in self.events]
        return kw


class BulkUnassignedMessage(AppealingMessageMixin, TypedTextPushMessage):
    message_type = 'BULK_JOBS_UNASSIGNED'
    message = ""

    def __init__(self, driver, events, *args, **kwargs):
        self.events = events
        self.driver = driver
        super(BulkUnassignedMessage, self).__init__(*args, **kwargs)

    def _get_appeal(self, *args, **kwargs):
        return self.driver.first_name

    def _get_postfix(self, *args, **kwargs):
        return _('{count} jobs were unassigned from you').format(count=len(self.events))

    def get_kwargs(self, version=1, *args, **kwargs):
        kw = super(BulkUnassignedMessage, self).get_kwargs(version, *args, **kwargs)
        if version == 1:
            kw['data']['orders_ids'] = [o.object.order_id for o in self.events]
        else:
            kw['data']['server_entity_ids'] = [o.object.id for o in self.events]
        return kw
