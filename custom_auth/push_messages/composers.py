from __future__ import absolute_import, unicode_literals

from django.utils.translation import ugettext_lazy as _

from notification.push_messages.composers import TypedTextPushMessage
from notification.push_messages.mixins import AppealingMessageMixin


class ForceLogoutPushMessage(AppealingMessageMixin, TypedTextPushMessage):
    message_type = 'FORCE_LOGOUT'
    message = _('you logged in')

    def __init__(self, driver, *args, **kwargs):
        self.driver = driver
        super(ForceLogoutPushMessage, self).__init__(*args, **kwargs)

    def _get_appeal(self, *args, **kwargs):
        return self.driver.first_name

    def _get_postfix(self, *args, **kwargs):
        return _(' on another device.')
