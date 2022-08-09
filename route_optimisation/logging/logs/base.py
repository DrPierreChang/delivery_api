from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

import pytz

from radaro_utils.helpers import to_timestamp

from ..const import EventType
from ..registry import log_item_registry


class LogItem:
    event = None

    def __init__(self, msg, event_kwargs, log_subject):
        self.event_kwargs = event_kwargs
        self.event_kwargs['msg'] = str(msg)
        self.log_subject = log_subject

    def write_in_log(self, optimisation_log, labels):
        log_obj = self.get_log_obj(labels)
        if 'full' in optimisation_log:
            optimisation_log['full'] += [log_obj]
        else:
            optimisation_log['full'] = [log_obj]

    def get_log_obj(self, labels):
        params = self.get_dict_params(**self.event_kwargs)
        return {
            'labels': labels,
            'timestamp': str(to_timestamp(timezone.now().astimezone(pytz.utc))),
            'level': 'dev',
            'event': self.event,
            'params': params,
        }

    def get_dict_params(self, **kwargs):
        return kwargs

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        raise NotImplementedError()

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        return cls.build_message(item, *args, **kwargs)


class VersionedLogItem(LogItem):
    current_version = 1

    def get_log_obj(self, labels):
        log_obj = super().get_log_obj(labels)
        log_obj['version'] = self.current_version
        return log_obj

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        version = item.get('version', 1)
        handler_name = 'build_message_for_web_v{number}'.format(number=version)
        handler = getattr(cls, handler_name, None)
        assert handler is not None, 'Implement {} for {}'.format(handler_name, cls.__name__)
        return handler(item, *args, **kwargs)

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        version = item.get('version', 1)
        handler_name = 'build_message_v{number}'.format(number=version)
        handler = getattr(cls, handler_name, None)
        assert handler is not None, 'Implement {} for {}'.format(handler_name, cls.__name__)
        return handler(item, *args, **kwargs)


@log_item_registry.register()
class SimpleMessage(LogItem):
    event = EventType.SIMPLE_MESSAGE

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        return item['params']['msg']


@log_item_registry.register()
class OldROObjectMessage(LogItem):
    event = EventType.OLD_RO

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        return _('Old type route optimisation')

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        old_id = item['params']['old_id']
        return _('Old type route optimisation') + '. Created from Old RO with id {}'.format(old_id)
