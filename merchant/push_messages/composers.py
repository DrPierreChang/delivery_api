from django.utils.translation import ugettext_lazy as _

from notification.push_messages.composers import TypedTextPushMessage
from notification.push_messages.mixins import AppealingMessageMixin


class BaseSkillSetPushMessage(AppealingMessageMixin, TypedTextPushMessage):

    def _get_appeal(self, *args, **kwargs):
        return self.driver.first_name

    def _get_message_part(self, *args, **kwargs):
        return _('skill set "{name}" {message}').format(name=self.skill_set.name, message=self.message)

    def _get_postfix(self, *args, **kwargs):
        return _(' by the manager {manager}').format(manager=self.manager.full_name)

    def __init__(self, driver, manager, skill_set, *args, **kwargs):
        self.driver = driver
        self.manager = manager
        self.skill_set = skill_set
        super(BaseSkillSetPushMessage, self).__init__(*args, **kwargs)

    def get_kwargs(self, *args, **kwargs):
        kw = super(BaseSkillSetPushMessage, self).get_kwargs(*args, **kwargs)
        kw['data']["update"] = {'skill_set_id': self.skill_set.id}
        return kw


class SkillSetAddedPushMessage(BaseSkillSetPushMessage):
    message_type = "SKILL_SET_ADDED"
    message = _('has been added to you')


class SkillSetRemovedPushMessage(BaseSkillSetPushMessage):
    message_type = "SKILL_SET_REMOVED"
    message = _('has been removed from you')
