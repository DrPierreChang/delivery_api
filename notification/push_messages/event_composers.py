from __future__ import absolute_import, unicode_literals

from notification.push_messages.base_composers import BasePushMessage
from notification.push_messages.mixins import DataMixin, TypeMixin


class EventMixin(object):
    DELETED = -1
    CREATED = 0
    MODEL_CHANGED = 2


class EventMessage(DataMixin, TypeMixin, BasePushMessage, EventMixin):
    MESSAGE_TYPE_CHOICES = {
        EventMixin.CREATED: {'message_type': "NEW_{}"},
        EventMixin.MODEL_CHANGED: {'message_type': "{}_CHANGED"},
        EventMixin.DELETED: {'message_type': "{}_REMOVED"}
    }

    def __init__(self, obj_preview, event, *args, **kwargs):
        super(EventMessage, self).__init__(*args, **kwargs)
        self.obj_preview = obj_preview
        self.event = event
    
    def get_message_type(self, *args, **kwargs):
        msg_template = self.MESSAGE_TYPE_CHOICES[self.event]['message_type']
        return msg_template.format(self.obj_preview['model'].upper())

    def get_kwargs(self, *args, **kwargs):
        kw = super(EventMessage, self).get_kwargs(*args, **kwargs)
        kw['data'].update(self.obj_preview)
        return kw
