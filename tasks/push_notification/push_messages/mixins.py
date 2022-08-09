from __future__ import absolute_import, unicode_literals

from notification.push_messages.mixins import MessageMixin


class VersionedOrderMessageMixin(MessageMixin):
    def __init__(self, order, *args, **kwargs):
        self.order = order

    def get_order(self, version, *args, **kwargs):
        kw = {
            'is_concatenated_order': self.order.is_concatenated_order,
        }
        if version == 1:
            kw['order_id'] = self.order.order_id
        else:
            kw['server_entity_id'] = self.order.id
        return kw

    def get_kwargs(self, version=1, *args, **kwargs):
        kw = super(VersionedOrderMessageMixin, self).get_kwargs(version, *args, **kwargs)
        kw['data'].update(self.get_order(version, *args, **kwargs))
        return kw
