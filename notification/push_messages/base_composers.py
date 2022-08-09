from __future__ import absolute_import, unicode_literals


class AbstractPushMessage(object):
    def get_kwargs(self, *args, **kwargs):
        raise NotImplementedError()


class BasePushMessage(AbstractPushMessage):
    def get_kwargs(self, *args, **kwargs):
        return {}
