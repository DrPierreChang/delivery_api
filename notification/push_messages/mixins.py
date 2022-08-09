from __future__ import absolute_import, unicode_literals

from django.conf import settings
from django.utils import translation

from notification.push_messages.base_composers import AbstractPushMessage


class MessageMixin(AbstractPushMessage):
    message = None

    def get_message(self, *args, **kwargs):
        return self.message

    def get_kwargs(self, version=1, *args, **kwargs):
        kw = super(MessageMixin, self).get_kwargs(*args, **kwargs)

        if version == settings.MOBILE_API_VERSION:
            language = kwargs.get('language', settings.LANGUAGE_CODE)
            with translation.override(language):
                text = self.get_message(*args, **kwargs)
        else:
            text = self.get_message(*args, **kwargs)

        kw['data'] = {
            'text': text
        }

        return kw


class TypeMixin(AbstractPushMessage):
    message_type = None

    def get_message_type(self, *args, **kwargs):
        return self.message_type

    def get_kwargs(self, *args, **kwargs):
        kw = super(TypeMixin, self).get_kwargs(*args, **kwargs)
        kw['type'] = self.get_message_type(*args, **kwargs)
        return kw


class DataMixin(AbstractPushMessage):
    def get_kwargs(self, *args, **kwargs):
        kw = super(DataMixin, self).get_kwargs(*args, **kwargs)
        kw['data'] = {}
        return kw


class AppealingMessageMixin(MessageMixin):
    def _get_appeal(self, *args, **kwargs):
        raise NotImplementedError()

    def _get_message_part(self, *args, **kwargs):
        return self.message

    def _get_postfix(self, *args, **kwargs):
        raise NotImplementedError()

    def get_message(self, *args, **kwargs):
        appeal = self._get_appeal(*args, **kwargs)
        msg = self._get_message_part(*args, **kwargs)
        postfix = self._get_postfix(*args, **kwargs)
        return self._compose_message(appeal, msg, postfix)

    def _compose_message(self, appeal, msg, postfix):
        return '{}, {}{}'.format(appeal, msg, postfix)
