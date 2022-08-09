from notification.push_messages.base_composers import BasePushMessage
from notification.push_messages.mixins import MessageMixin, TypeMixin


class TypedTextPushMessage(MessageMixin, TypeMixin, BasePushMessage):
    pass
