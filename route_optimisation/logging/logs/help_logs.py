from django.utils.translation import ugettext_lazy as _

from route_optimisation.const import OPTIMISATION_TYPES

from ..const import EventType
from ..registry import log_item_registry
from .base import LogItem, VersionedLogItem


@log_item_registry.register()
class AssignedOrdersLog(VersionedLogItem):
    event = EventType.ASSIGNED_AFTER_RO
    current_version = 2

    @classmethod
    def build_message_for_web_v1(cls, item, *args, **kwargs):
        count = len(item['params']['orders'])
        driver_full_name = item['params']['driver_full_name']
        return '{} job{} {} assigned to {} during the {}' \
            .format(count, 's' if count > 1 else '', 'were' if count > 1 else 'was', driver_full_name,
                    _('Optimisation'))

    @classmethod
    def build_message_for_web_v2(cls, item, *args, **kwargs):
        return cls.build_message_v2(item, *args, **kwargs)

    @classmethod
    def build_message_v1(cls, item, *args, **kwargs):
        orders = item['params']['orders']
        driver_full_name = item['params']['driver_full_name']
        return 'Assigned orders with ids {} to driver {}.'.format(', '.join(map(str, orders)), driver_full_name)

    @classmethod
    def build_message_v2(cls, item, optimisation, *args, **kwargs):
        all_count = item['params']['count']
        assigned_count = len(item['params']['assigned'])
        previously_assigned_count = len(item['params']['previously_assigned'])
        driver_full_name = item['params']['driver_full_name']
        if optimisation.type == OPTIMISATION_TYPES.SOLO:
            if all_count == 0:
                return
            plural, was_plural = ('s', 'were') if all_count > 1 else ('', 'was')
            return '{} job{} {} included into {}'.format(all_count, plural, was_plural, _('Optimisation'))

        if assigned_count + previously_assigned_count == 0:
            return
        new_jobs_msg, old_jobs_msg = None, None
        if assigned_count:
            plural, was_plural = ('s', 'were') if assigned_count > 1 else ('', 'was')
            new_jobs_msg = '{} new job{} {} assigned to {}'.format(assigned_count, plural, was_plural,
                                                                   driver_full_name)
        if previously_assigned_count:
            plural, was_plural = ('s', 'were') if previously_assigned_count > 1 else ('', 'was')
            driver_info = ' for driver {}'.format(driver_full_name)
            old_jobs_msg = '{} job{} {} re-optimised{}'.format(previously_assigned_count, plural, was_plural,
                                                               driver_info if not new_jobs_msg else '')
        msg = ' and '.join(filter(None, (new_jobs_msg, old_jobs_msg)))
        return '{} during the {}'.format(msg, _('Optimisation'))

    def get_dict_params(self, driver, **kwargs):
        params = super().get_dict_params(**kwargs)
        params.update({
            'driver_full_name': driver.full_name,
            'driver_id': driver.id,
        })
        return params


@log_item_registry.register()
class SkippedObjectsLog(LogItem):
    event = EventType.SKIPPED_OBJECTS

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        count = len(item['params']['objects'])
        code = item['params'].get('code')
        plural, this_plural, was_plural, is_plural = ('s', 'these', 'were', 'are') \
            if count > 1 else ('', 'this', 'was', 'is')
        if code == 'order':
            return '{} job{} {} left out of the {}. ' \
                   'All available drivers have been provided with routes at their full capacity' \
                .format(count, plural, was_plural, _('Optimisation'))
        if code == 'not_accessible_orders':
            return '{} job{} {} left out of the {}. ' \
                   '{} job{} {} not accessible by geographical reasons' \
                .format(count, plural, was_plural, _('Optimisation'), this_plural.capitalize(), plural, is_plural)
        if code == 'not_accessible_drivers':
            return '{} driver{} {} left out of the {}. ' \
                   '{} driver{} {} not accessible by geographical reasons' \
                .format(count, plural, was_plural, _('Optimisation'), this_plural.capitalize(), plural, is_plural)
        if code == 'driver':
            return '{} driver{} {} left out of the {}: all jobs were assigned between other drivers' \
                .format(count, plural, was_plural, _('Optimisation'))

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        message = 'None'
        objects = item['params']['objects']
        code = item['params'].get('code')
        count = len(objects)
        plural, this_plural, was_plural, is_plural = ('s', 'these', 'were', 'are') \
            if count > 1 else ('', 'this', 'was', 'is')
        if code == 'order':
            return '{} order{} {} skipped: {}'.format(count, plural, is_plural, objects,)
        if code == 'not_accessible_orders':
            return '{} order{} {} not accessible by geographical reasons so skipped: {}'.format(
                count, plural, is_plural, objects)
        if code == 'not_accessible_drivers':
            return '{} driver{} {} not accessible by geographical reasons so skipped: {}'.format(
                count, plural, is_plural, objects)
        if code == 'driver':
            return '{} driver{} {} skipped: {}'.format(count, plural, is_plural, objects,)
        return message

    def get_dict_params(self, objects, **kwargs):
        params = super().get_dict_params(**kwargs)
        params.update({
            'objects': list(objects),
        })
        return params


@log_item_registry.register()
class NotifyCustomersLog(LogItem):
    event = EventType.NOTIFY_CUSTOMERS

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        code = item['params']['code']
        if code == 'success':
            return 'Customers were notified about the upcoming jobs!'

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        code = item['params']['code']
        if code == 'request':
            initiator_full_name = item['params']['initiator_full_name']
            initiator_id = item['params']['initiator_id']
            return 'Request to notify customers by user "{}" with id {}'.format(initiator_full_name, initiator_id)
        if code == 'success':
            return 'Customers are notified'

    def get_dict_params(self, initiator=None, **kwargs):
        params = super().get_dict_params(**kwargs)
        if initiator:
            params.update({
                'initiator_full_name': initiator.full_name,
                'initiator_id': initiator.id,
            })
        return params


@log_item_registry.register()
class RemoveRoutePointLog(LogItem):
    event = EventType.REMOVE_ROUTE_POINT

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        model = item['params']['model']
        point_kind = item['params'].get('point_kind', '')
        event_type = item['params']['event_type']

        event_types = {
            'delete': 'deleted',
            'unassign': 'unassigned',
        }
        event = event_types.get(event_type.lower(), 'changed')
        point_str = '1 {}{}route point'.format(point_kind, ' ' if point_kind else '', '')

        return '{} was removed from the {}: {} has been {}' \
            .format(point_str, _('Optimisation'), model, event)

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        model = item['params']['model']
        obj_id = item['params']['obj_id']
        point_kind = item['params'].get('point_kind', '')
        event_type = item['params']['event_type']

        event_types = {
            'delete': 'deleted',
            'unassign': 'unassigned',
        }
        event_message = event_types.get(event_type.lower(), 'changed')
        obj_str = '{type} with id {id}'.format(type=model.capitalize(), id=obj_id)
        point_str = 'Removed {}{}route point'.format(point_kind, ' ' if point_kind else '', '')

        return '%s was %s. %s, changed numbers of other points in driver route' \
               % (obj_str, event_message, point_str)


@log_item_registry.register()
class DeleteROLog(LogItem):
    event = EventType.DELETE_RO

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        return DeleteROLog._build_remove_optimisation_log_message(**item['params'])

    def get_dict_params(self, initiator=None, **kwargs):
        params = super().get_dict_params(**kwargs)
        params.update({
            'initiator_full_name': initiator.full_name if initiator else None,
            'initiator_is_driver': initiator.is_driver if initiator else None,
            'initiator_id': initiator.id if initiator else None,
        })
        return params

    @staticmethod
    def _build_remove_optimisation_log_message(unassign, initiator_full_name, initiator_is_driver, initiator_id,
                                               unassigned_count=None, cms_user=False, *args, **kwargs):
        additional_message = ''
        if unassign and unassigned_count is not None and unassigned_count > 0:
            if unassigned_count == 1:
                additional_message = '1 job was'
            else:
                additional_message = '{} jobs were'.format(unassigned_count)
            additional_message = '. {} unassigned'.format(additional_message)

        initiator_message = ''
        if initiator_id:
            if cms_user:
                initiator_message = ' by CMS User {}'.format(initiator_full_name)
            else:
                initiator_message = ' by {} {}'.format('driver' if initiator_is_driver else 'manager',
                                                       initiator_full_name)

        return '{} was removed{}{}'.format(_('Optimisation'), initiator_message, additional_message)


@log_item_registry.register()
class TrackApiStatisticLog(LogItem):
    event = EventType.TRACK_API_STAT

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        return None

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        return 'Track google api requests: {}'.format(item['params']['stat'])


@log_item_registry.register()
class RefreshOptimisationOptionsLog(LogItem):
    event = EventType.REFRESH_OPTIONS

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        return None

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        return 'Successful refresh optimisation options.\n{}'.format(item['params']['optimisation_options'])


@log_item_registry.register()
class TerminateOptimisationLog(LogItem):
    event = EventType.TERMINATE_RO

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        initiator_full_name = item['params']['initiator_full_name']
        initiator_role = item['params']['initiator_role']
        initiator_postfix = f' by {initiator_role} {initiator_full_name}' \
            if initiator_role and initiator_full_name else ''
        return 'Optimisation terminated' + initiator_postfix

    def get_dict_params(self, initiator=None, **kwargs):
        params = super().get_dict_params()
        params.update({
            'initiator_full_name': initiator.full_name if initiator else None,
            'initiator_role': initiator.get_role_display().lower() if initiator else None
        })
        return params


@log_item_registry.register()
class FillPolylinesMessage(LogItem):
    event = EventType.FILL_POLYLINES

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        return None

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        return 'Polylines refreshed'
