from operator import attrgetter

from django.utils.translation import ugettext_lazy as _

from ..const import EventType
from ..registry import log_item_registry
from .base import LogItem


@log_item_registry.register()
class ReorderedSequenceMessage(LogItem):
    event = EventType.REORDER_SEQUENCE

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        return cls.build_message(item, *args, **kwargs)

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        return 'Sequence of route {} for {} changed by {}'.format(
            item['params']['route_id'], item['params']['driver_full_name'], item['params']['initiator_full_name'],
        )

    def get_dict_params(self, route, initiator, **kwargs):
        params = super().get_dict_params(**kwargs)
        params.update({
            'route_id': route.id,
            'driver_full_name': route.driver.full_name,
            'driver_id': route.driver.id,
            'initiator_full_name': initiator.full_name,
            'initiator_id': initiator.id,
        })
        return params


@log_item_registry.register()
class MoveJobsMessage(LogItem):
    event = EventType.MOVE_JOBS

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        return cls.build_message(item, *args, **kwargs)

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        jobs_count = len(item['params']['jobs_ids'])
        plural = 's' if jobs_count > 1 else ''
        tmpl = 'Moved {jobs_count} job{plural} from route of driver {from_driver} ' \
               'to route of driver {target_driver} by {initiator}'
        return tmpl.format(
            jobs_count=jobs_count, plural=plural, from_driver=item['params']['source_driver_full_name'],
            target_driver=item['params']['target_driver_full_name'], initiator=item['params']['initiator_full_name'],
        )

    def get_dict_params(self, source_route, target_route, jobs, initiator, **kwargs):
        params = super().get_dict_params(**kwargs)
        params.update({
            'source_route_id': source_route.id,
            'target_route_id': target_route.id,
            'jobs_ids': list(map(attrgetter('id'), jobs)),
            'source_driver_full_name': source_route.driver.full_name,
            'source_driver_id': source_route.driver.id,
            'target_driver_full_name': target_route.driver.full_name,
            'target_driver_id': target_route.driver.id,
            'initiator_full_name': initiator.full_name,
            'initiator_id': initiator.id,
        })
        return params


@log_item_registry.register()
class OptimisationCreatedChangeMessage(LogItem):
    event = EventType.CREATE_RO_AFTER_MOVE_JOBS

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        return cls.build_message(item, *args, **kwargs)

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        return '{} created after moving jobs from another driver by {}'.format(
            _('Optimisation'), item['params']['initiator_full_name']
        )

    def get_dict_params(self, source_route, target_route, initiator, **kwargs):
        params = super().get_dict_params(**kwargs)
        params.update({
            'source_route_id': source_route.id,
            'target_route_id': target_route.id,
            'initiator_full_name': initiator.full_name,
            'initiator_id': initiator.id,
        })
        return params
