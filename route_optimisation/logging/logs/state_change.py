from django.utils.translation import ugettext_lazy as _

from ..const import EventType
from ..registry import log_item_registry
from .base import LogItem


@log_item_registry.register()
class OptimisationStateChangeMessage(LogItem):
    event = EventType.RO_STATE_CHANGE

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        from route_optimisation.models import RouteOptimisation
        if item['params']['state'] == RouteOptimisation.STATE.VALIDATION:
            return '{} started'.format(_('Optimisation'))
        return None

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        return 'State changed to "{}"'.format(item['params']['state'])


@log_item_registry.register()
class RouteStateChangeMessage(LogItem):
    event = EventType.ROUTE_STATE_CHANGE

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        return None

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        return 'Route {} state changed to "{}"'.format(item['params']['route_id'], item['params']['state'])

    def get_dict_params(self, route, **kwargs):
        params = super().get_dict_params(**kwargs)
        params.update({
            'route_id': route.id,
        })
        return params


@log_item_registry.register()
class RefreshStateChangeMessage(LogItem):
    event = EventType.REFRESH_STATE_CHANGE

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        from route_optimisation.models import RouteOptimisation
        if item['params']['state'] == RouteOptimisation.STATE.VALIDATION:
            return '{} refresh started. Initiated by {}'.format(
                _('Optimisation'), item['params']['initiator_full_name']
            )
        elif item['params']['state'] == RouteOptimisation.STATE.FAILED:
            return '{} refresh failed'.format(_('Optimisation'))
        elif item['params']['state'] == RouteOptimisation.STATE.COMPLETED:
            return '{} refresh completed'.format(_('Optimisation'))

    def get_dict_params(self, initiator, **kwargs):
        params = super().get_dict_params(**kwargs)
        params.update({
            'initiator_full_name': initiator.full_name,
            'initiator_id': initiator.id,
        })
        return params
