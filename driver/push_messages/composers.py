from __future__ import absolute_import, unicode_literals

from django.utils.translation import ugettext_lazy as _

from driver.utils import WorkStatus
from notification.push_messages.composers import TypedTextPushMessage
from notification.push_messages.mixins import AppealingMessageMixin


class ForceOfflinePushMessage(AppealingMessageMixin, TypedTextPushMessage):
    message_type = "FORCED_UPDATE_BY_MANAGER"
    message = _('you have been forced offline')

    def _get_appeal(self, *args, **kwargs):
        return self.driver.first_name

    def _get_postfix(self, *args, **kwargs):
        return _(' by the manager {manager}').format(manager=self.manager.full_name)

    def __init__(self, driver, manager, *args, **kwargs):
        self.driver = driver
        self.manager = manager
        super(ForceOfflinePushMessage, self).__init__(*args, **kwargs)

    def get_kwargs(self, *args, **kwargs):
        kw = super(ForceOfflinePushMessage, self).get_kwargs(*args, **kwargs)
        kw['data']['update'] = {'is_online': False, 'work_status': WorkStatus.NOT_WORKING}
        return kw
