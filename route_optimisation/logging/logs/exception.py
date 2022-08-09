from django.utils.translation import ugettext_lazy as _

from ..const import EventType
from ..registry import log_item_registry
from .base import LogItem


@log_item_registry.register()
class ExceptionLog(LogItem):
    event = EventType.EXCEPTION

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        code = item['params']['code']
        if code == 'ro_error':
            if 'NoSolutionFoundError' in item['params']['exc_type']:
                return 'No solution was found for this Optimisation'
            elif 'ROError' in item['params']['exc_type']:
                return item['params']['exc_str']
        if code in ('time_limit', 'unknown'):
            return 'Oops, something went wrong...'

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        message = 'None'
        code = item['params']['code']
        if code == 'ro_error':
            exc_type = item['params']['exc_type']
            exc_str = item['params']['exc_str']
            return 'RO error occurred. {}. {}.'.format(exc_type, exc_str)
        if code == 'time_limit':
            return 'Optimisation time exceeded. Optimisation cancelled.'
        if code == 'unknown':
            exc_type = item['params']['exc_type']
            exc_str = item['params']['exc_str']
            return 'Unknown error occurred. {}. {}.'.format(exc_type, exc_str)
        return message

    def get_dict_params(self, exc=None, exc_dict=None, **kwargs):
        params = super().get_dict_params(**kwargs)
        if exc:
            params.update({
                'exc_type': str(type(exc)),
                'exc_str': str(exc),
            })
        elif exc_dict is not None:
            params.update({
                'exc_type': exc_dict['exc_type'],
                'exc_str': exc_dict['exc_str'],
            })
        return params


@log_item_registry.register()
class ExceptionOnDeletionLog(LogItem):
    event = EventType.EXCEPTION_ON_DELETION

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        return 'Oops, something went wrong while removing {}. Consider try again.'.format(_('Optimisation'))

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        exc_type = item['params']['exc_type']
        exc_str = item['params']['exc_str']
        return 'Unknown error occurred while removing Optimisation. {}. {}.'.format(exc_type, exc_str)

    def get_dict_params(self, exc=None, **kwargs):
        params = super().get_dict_params(**kwargs)
        if exc:
            params.update({
                'exc_type': str(type(exc)),
                'exc_str': str(exc),
            })
        return params
