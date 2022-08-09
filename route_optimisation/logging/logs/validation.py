from typing import List

from django.utils.translation import ugettext_lazy as _

from route_optimisation.const import OPTIMISATION_TYPES

from ..const import EventType
from ..registry import log_item_registry
from .base import LogItem


@log_item_registry.register()
class ObjectNotFoundLog(LogItem):
    event = EventType.OBJECT_NOT_FOUND

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        return None

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        model = item['params']['model']
        obj_id = item['params']['obj_id']
        lookup_field = item['params'].get('lookup_field', 'id')
        return '{} with {} {} not found'.format(model.capitalize(), lookup_field, obj_id)


@log_item_registry.register()
class ValidationErrorLog(LogItem):
    event = EventType.VALIDATION_ERROR

    @classmethod
    def build_message_for_web(cls, item, optimisation, preceding_valid_items: List[LogItem], *args, **kwargs):
        code = item['params']['code']
        if code == 'no_drivers' and cls._should_ignore_message(optimisation, preceding_valid_items):
            return None
        return super().build_message_for_web(item, optimisation, preceding_valid_items, *args, **kwargs)

    @staticmethod
    def _should_ignore_message(optimisation, preceding_valid_items):
        if optimisation.type != OPTIMISATION_TYPES.SOLO:
            return False
        for log_item in preceding_valid_items:
            if log_item.get('event') == EventType.DRIVER_NOT_AVAILABLE:
                return True
            if log_item.get('event') == EventType.DRIVER_TIME:
                messages = log_item['params']['messages']
                for code, *other in messages:
                    if code == 'no_time':
                        return True
        return False

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        code = item['params']['code']
        if code == 'no_jobs':
            return 'There are no jobs selected to create an {}'.format(_('Optimisation'))
        if code == 'many_jobs':
            count = item['params'].get('count')
            max_count = item['params'].get('max_count')
            return 'Too many jobs were selected to create an {optimisation}. ' \
                   'Please make sure that the number of jobs is not exceeding {} ' \
                   '(you were trying to create an {optimisation} with {} jobs)'\
                .format(max_count, count, optimisation=_('Optimisation'))
        if code == 'no_drivers':
            return 'There are no drivers available to create an {}'.format(_('Optimisation'))
        if code == 'working_hours':
            return 'Unable to create an {} with a working time interval that includes the time in the past'\
                .format(_('Optimisation'))
        if code == 'refresh_options_equals':
            return 'Nothing to refresh. Everything is already {}'.format(_('optimised'))


@log_item_registry.register()
class JobFilteredOutLog(LogItem):
    event = EventType.JOB_FILTERED

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        jobs = item['params']['jobs']
        code = item['params']['code']
        count = len(jobs)
        plural, this_plural, was_plural, is_plural = ('s', 'these', 'were', 'are') \
            if count > 1 else ('', 'this', 'was', 'is')
        if code == 'working_hours':
            return '{} job{} {} removed from the {optimisation}: ' \
                   'deadlines are out of working hours for this {optimisation}'\
                .format(count, plural, was_plural, optimisation=_('Optimisation'))
        elif code == 'other_optimisations':
            return '{} job{plural} {was_plural} removed from the {optimisation}: ' \
                   '{this_plural} job{plural} {is_plural} already accounted in another {optimisation}'\
                .format(count, was_plural=was_plural, this_plural=this_plural, plural=plural, is_plural=is_plural,
                        optimisation=_('Optimisation'))
        elif code == 'driver_not_available':
            return '{} job{} {} removed from the {optimisation}: ' \
                   'job\'s assigned driver is unavailable for this {optimisation}'\
                .format(count, plural, was_plural, optimisation=_('Optimisation'))
        elif code == 'skill_set':
            return '{} job{} {} left out of the {optimisation}: ' \
                   'no drivers with matching skill sets were found'\
                .format(count, plural, was_plural, optimisation=_('Optimisation'))
        elif code == 'miss_drivers_schedule':
            return '{} job{} {} removed from the {optimisation}: ' \
                   'deadlines are out of driver\'s schedule for this day'\
                .format(count, plural, was_plural, optimisation=_('Optimisation'))

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        message = 'None'
        jobs = item['params']['jobs']
        code = item['params']['code']
        if code == 'wrong_day':
            message = 'Filter out by wrong day {} jobs with: {}.'.format(
                len(jobs), '; '.join(map(lambda x: 'id:%s,status:%s' % (x['id'], x['status']), jobs))
            )
        elif code == 'working_hours':
            message = 'Filter out by working hours option {} jobs with: {}.'.format(
                len(jobs), '; '.join(map(lambda x: 'id:%s,deliver_after:%s,deliver_before:%s'
                                                   % (x['id'], x['deliver_after'], x['deliver_before']),
                                         jobs))
            )
        elif code == 'other_optimisations':
            message = 'Filter out because used in other {} {} jobs with ids: {}.'.format(
                _('optimisation'), len(jobs), '; '.join(map(lambda x: 'id:%s' % x['id'], jobs))
            )
        elif code == 'status':
            message = 'Filter out by status {} jobs with: {}.'.format(
                len(jobs), '; '.join(map(lambda x: 'id:%s,status:%s' % (x['id'], x['status']), jobs))
            )
        elif code == 'driver_not_available':
            message = 'Filter out {} assigned jobs with not available driver with ids: {}.'.format(
                len(jobs), ','.join(map(lambda x: str(x['id']), jobs))
            )
        elif code == 'skill_set':
            message = 'Filter out {} jobs because there is no drivers with good skill set. Jobs ids: {}.'.format(
                len(jobs), ','.join(map(lambda x: str(x['id']), jobs))
            )
        elif code == 'miss_drivers_schedule':
            message = 'Filter out {} jobs because deadlines are out of driver\'s schedule. Jobs ids: {}.'.format(
                len(jobs), ','.join(map(lambda x: str(x['id']), jobs))
            )
        return message

    def get_dict_params(self, jobs=None, **kwargs):
        params = super().get_dict_params(**kwargs)
        params.update({
            'jobs': [{'id': job.id, 'status': job.status, 'deliver_before': str(job.deliver_before),
                      'deliver_after': str(job.deliver_after) if job.deliver_after else None}
                     for job in jobs]
        })
        return params


@log_item_registry.register()
class JobAddedLog(LogItem):
    event = EventType.JOB_ADDED

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        return None

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        message = 'None'
        jobs = item['params']['jobs']
        code = item['params']['code']
        if code == 're_optimise_assigned':
            message = 'Added by re_optimise_assigned option {} jobs with ids: {}.'.format(
                len(jobs), ','.join(map(lambda x: str(x['id']), jobs))
            )
        return message

    def get_dict_params(self, jobs=None, **kwargs):
        params = super().get_dict_params(**kwargs)
        params.update({
            'jobs': [{'id': job.id, 'status': job.status, 'deliver_before': str(job.deliver_before),
                      'deliver_after': str(job.deliver_after) if job.deliver_after else None}
                     for job in jobs]
        })
        return params


@log_item_registry.register()
class DriverNotAvailableLog(LogItem):
    event = EventType.DRIVER_NOT_AVAILABLE

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        driver_full_name = item['params']['driver_full_name']
        code = item['params']['code']
        if code in ('start_hub', 'end_hub'):
            return 'Driver {} hasn\'t set a default hub and will be removed from the {}' \
                .format(driver_full_name, _('Optimisation'))
        elif code in ('start_point', 'end_point'):
            return 'Driver {} hasn\'t set a default point and will be removed from the {}' \
                .format(driver_full_name, _('Optimisation'))
        elif code == 'no_schedule':
            return 'Driver {} is unavailable during the {} working hours and will be removed' \
                .format(driver_full_name, _('Optimisation'))
        elif code == 'skill_set':
            return 'Driver {} was left out of the {}: no jobs with matching skill sets were found' \
                .format(driver_full_name, _('Optimisation'))

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        message = 'None'
        driver_full_name = item['params']['driver_full_name']
        driver_id = item['params']['driver_id']
        code = item['params']['code']
        if code == 'start_hub':
            message = 'Driver {} with id {} has no default starting hub.'.format(driver_full_name, driver_id)
        elif code == 'start_point':
            message = 'Driver {} with id {} has no default starting point.'.format(driver_full_name, driver_id)
        elif code == 'end_hub':
            message = 'Driver {} with id {} has no default ending hub.'.format(driver_full_name, driver_id)
        elif code == 'end_point':
            message = 'Driver {} with id {} has no default ending point.'.format(driver_full_name, driver_id)
        elif code == 'no_schedule':
            message = 'Driver {} with id {} has no schedule for this day.'.format(driver_full_name, driver_id)
        elif code == 'skill_set':
            message = 'Driver {} with id {} is not satisfying jobs skill sets.'.format(driver_full_name, driver_id)
        return message

    def get_dict_params(self, driver=None, **kwargs):
        params = super().get_dict_params(**kwargs)
        params.update({
            'driver_full_name': driver.full_name,
            'driver_id': driver.id,
        })
        return params


@log_item_registry.register()
class DriverTimeLog(LogItem):
    event = EventType.DRIVER_TIME

    @classmethod
    def build_message_for_web(cls, item, *args, **kwargs):
        driver_full_name = item['params']['driver_full_name']
        messages = item['params']['messages']
        for code, *other in messages:
            if code == 'no_time':
                return 'Driver {} is unavailable during the {} working hours and will be removed'\
                    .format(driver_full_name, _('Optimisation'))

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        driver_full_name = item['params']['driver_full_name']
        driver_id = item['params']['driver_id']
        messages = item['params']['messages']
        message = ''
        for m in messages:
            if m[0] == 'initial':
                message += 'Driver {} with id {} has schedule from {} to {}.\n'.format(driver_full_name, driver_id,
                                                                                       *m[1:])
            elif m[0] == 'passed_start_time':
                old, new = m[1:]
                message += 'Change min time to {} because {} already passed.\n'.format(new, old)
            elif m[0] == 'passed_end_time':
                end_time, min_start_from = m[1:]
                message += 'Exclude driver\'s time because end time {} already passed.\n'.format(end_time)
            elif m[0] == 'working_hours_lower':
                message += 'Change min time to {} by working_hours option.\n'.format(*m[1:])
            elif m[0] == 'working_hours_upper':
                message += 'Change max time to {} by working_hours option.\n'.format(*m[1:])
            elif m[0] == 'working_hours_exclude':
                message += 'Exclude driver time by working_hours option.\n'
            elif m[0] == 'exclude_time':
                message += 'Exclude time from {} to {} by route {} from optimisation {}.\n'.format(*m[1:])
            elif m[0] == 'exclude_time_by_option':
                message += 'Exclude time from {} to {} by driver {} option from optimisation {}.\n'.format(*m[1:])
            elif m[0] == 'driver_break_exclude':
                message += 'Exclude driver time by driver break({}-{}).\n'.format(*m[1:])
            elif m[0] == 'driver_break_lower':
                message += 'Change min time to {} by driver break({}-{}).\n'.format(*m[1:])
            elif m[0] == 'driver_break_upper':
                message += 'Change max time to {} by driver break({}-{}).\n'.format(*m[1:])
            elif m[0] == 'leave_time':
                message += 'Leave time from {} to {}.\n'.format(*m[1:])
            elif m[0] == 'no_time':
                message += 'No time left.\n'
        return message.strip()

    def get_dict_params(self, driver, messages, **kwargs):
        params = super().get_dict_params(**kwargs)
        params.update({
            'driver_full_name': driver.full_name,
            'driver_id': driver.id,
        })
        _msg = []
        for m in messages:
            if m[0] == 'exclude_time':
                _from, _to, route, optimisation = m[1:]
                _msg.append((m[0], str(_from), str(_to), route.id, optimisation.id))
            elif m[0] == 'exclude_time_by_option':
                _from, _to, driver_id, optimisation = m[1:]
                _msg.append((m[0], str(_from), str(_to), driver_id, optimisation.id))
            elif m[0] in ('leave_time', 'initial', 'passed_end_time', 'passed_start_time',):
                _from, _to = m[1:]
                _msg.append((m[0], str(_from), str(_to)))
            elif m[0] in ('working_hours_lower', 'working_hours_upper'):
                _time = m[1]
                _msg.append((m[0], str(_time)))
            elif m[0] in ('driver_break_exclude', 'driver_break_lower', 'driver_break_upper'):
                _times = m[1:]
                _msg.append((m[0], *map(str, _times)))
            else:
                _msg.append(m)
        params['messages'] = _msg
        return params
