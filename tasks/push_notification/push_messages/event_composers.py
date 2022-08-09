from __future__ import absolute_import, unicode_literals

from django.utils.translation import ugettext_lazy as _

from notification.push_messages.composers import TypedTextPushMessage

from .mixins import VersionedOrderMessageMixin
from .order_change_status_composers import OrderStatusChangeMessage


class OrderDeletedMessage(OrderStatusChangeMessage):
    job_prefix = _('your job')

    def get_message_type(self, *args, **kwargs):
        return 'JOB_DELETED'

    def _get_job_name(self, *args, **kwargs):
        return self.order['title']

    def _get_postfix(self, *args, **kwargs):
        return _(' has been deleted')

    def get_order(self, version, *args, **kwargs):
        kw = {
            'is_concatenated_order': self.order['is_concatenated_order'],
        }
        if version == 1:
            kw['order_id'] = self.order['order_id']
        else:
            kw['server_entity_id'] = self.order['id']
        return kw


class OrderChangedMessage(VersionedOrderMessageMixin, TypedTextPushMessage):
    message_type = 'JOB_CHANGED'
    message = _('{appeal}, your job \"{title}\" has been updated with new info')

    def get_message(self, *args, **kwargs):
        return self.message.format(appeal=self.order.driver.first_name, title=self.order.title)


class ChecklistMessage(VersionedOrderMessageMixin, TypedTextPushMessage):
    message_type = 'OPEN_CHECKLIST'
    message = _('Seems, that you\'ve arrived at job location. Please carry out the {checklist}')
    nti_message = _('You\'ve arrived at your job. Please carry out the {checklist}')

    def get_message(self, *args, **kwargs):
        message = self.nti_message if self.order.merchant.is_nti else self.message
        return message.format(checklist=self.order.driver_checklist.title)


class JobDeadlineMessage(VersionedOrderMessageMixin, TypedTextPushMessage):
    message = _("{appeal}, your job \"{title}\" deadline has expired")
    message_type = "JOB_DEADLINE"

    def get_message(self, *args, **kwargs):
        return self.message.format(appeal=self.order.driver.first_name, title=self.order.title)


class JobSoonDeadlineMessage(JobDeadlineMessage):
    message = _("You have less than 30 minutes to finish job \"{title}\"")

    def get_message(self, *args, **kwargs):
        return self.message.format(title=self.order.title)


class OrderCargoesChangedMessage(VersionedOrderMessageMixin, TypedTextPushMessage):
    message_type = 'JOB_CARGOES_CHANGED'
    message = _("SKID info in job \"{title}\" has been updated")

    def get_message(self, *args, **kwargs):
        return self.message.format(title=self.order.title)


class OrderAddedToConcatenatedMessage(VersionedOrderMessageMixin, TypedTextPushMessage):
    message_type = 'JOB_ADDED_TO_CONCATENATED'
    message = _('{appeal}, your job "{title}" has been added to concatenated job')

    def get_message(self, *args, **kwargs):
        return self.message.format(appeal=self.order.driver.first_name, title=self.order.title)


class OrderRemovedFromConcatenatedMessage(VersionedOrderMessageMixin, TypedTextPushMessage):
    message_type = 'JOB_REMOVED_FROM_CONCATENATED'
    message = _('{appeal}, your job "{title}" has been removed from concatenated job')

    def __init__(self, driver, *args, **kwargs):
        self.driver = driver
        super().__init__(*args, **kwargs)

    def get_message(self, *args, **kwargs):
        return self.message.format(appeal=self.driver.first_name, title=self.order.title)


class ConcatenatedOrderUngroupedMessage(VersionedOrderMessageMixin, TypedTextPushMessage):
    message_type = 'CONCATENATED_JOB_UNGROUPED'
    message = _('{appeal}, your concatenated job has been ungrouped')

    def get_message(self, *args, **kwargs):
        return self.message.format(appeal=self.order.driver.first_name)


class ConcatenatedOrderGroupedMessage(VersionedOrderMessageMixin, TypedTextPushMessage):
    message_type = 'CONCATENATED_JOB_GROUPED'
    message = _('{appeal}, your jobs have been grouped into concatenated job')

    def get_message(self, *args, **kwargs):
        return self.message.format(appeal=self.order.driver.first_name)
