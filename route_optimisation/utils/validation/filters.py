import logging
from datetime import datetime, timedelta
from operator import attrgetter

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_time

from route_optimisation.const import CONTEXT_HELP_ITEM, HubOptions
from route_optimisation.logging import EventType
from schedule.models import Schedule
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

logger = logging.getLogger('optimisation')


class PipeBase:
    def __init__(self, optimisation, options, context):
        self.optimisation = optimisation
        self.options = options
        self.context = context

    def __call__(self, *args, **kwargs):
        raise NotImplementedError()


class FilterBase(PipeBase):
    key = None

    def _prepare(self):
        pass

    def _filter_out(self, objects):
        return []

    def _process_filtered_out(self, objects):
        pass

    def _active(self):
        return True

    def __call__(self):
        if not self._active():
            return
        self._prepare()
        objects = self.options.pop(self.key, [])
        filtered_out = list(self._filter_out(objects))
        self.options[self.key] = [obj for obj in objects if obj not in filtered_out]
        if filtered_out:
            self._process_filtered_out(filtered_out)


class DriverTimeFilter(FilterBase):
    key = 'drivers_ids'

    def _filter_out(self, objects):
        for driver in objects:
            allowed_period, messages = self._get_allowed_period(driver)

            if not allowed_period:
                messages.append(('no_time',))
            else:
                messages.append(('leave_time', allowed_period[0], allowed_period[1]))
            logger.info(None, extra=dict(obj=self.optimisation, event=EventType.DRIVER_TIME,
                                         event_kwargs={'driver': driver, 'messages': messages}))

            driver.allowed_period = allowed_period
            if driver.allowed_period is None:
                yield driver

    def _get_allowed_period(self, driver):
        messages = []

        driver_working_hours, msgs = self._get_driver_working_hours(driver)
        messages += msgs
        if not driver_working_hours:
            return None, messages

        driver_working_hours, msgs = self._process_by_current_time(driver_working_hours)
        messages += msgs
        if not driver_working_hours:
            return None, messages

        driver_working_hours, msgs = self._process_by_ro_working_hours(driver_working_hours)
        messages += msgs
        if not driver_working_hours:
            return None, messages

        driver_working_hours, msgs = self._process_by_driver_breaks(driver_working_hours, driver)
        messages += msgs
        if not driver_working_hours:
            return None, messages

        driver_working_hours, msgs = self._process_by_routes(driver, driver_working_hours)
        messages += msgs
        if not driver_working_hours:
            return None, messages

        return driver_working_hours, messages

    def _process_by_routes(self, driver, working_hours):
        messages = []
        driver_period = [working_hours]
        exclude_periods = []
        tz = self.optimisation.merchant.timezone

        for optimisation in self.context[CONTEXT_HELP_ITEM].get('in_process_optimisations', []):
            if not optimisation.optimisation_options:
                continue
            driver_option = [d for d in optimisation.optimisation_options['drivers'] if d['id'] == driver.id]
            if not driver_option:
                continue
            driver_option = driver_option[0]
            exclude_time = (
                self._time_to_datetime(parse_time(driver_option['start_time'])) - timedelta(hours=1),
                self._time_to_datetime(parse_time(driver_option['end_time'])) + timedelta(hours=1)
            )
            message_detail = (driver_option['id'], optimisation)
            exclude_periods.append((exclude_time, 'exclude_time_by_option', message_detail))

        for optimisation in self.context[CONTEXT_HELP_ITEM].get('day_optimisations', []):
            for route in optimisation.routes.all():
                if route.driver_id == driver.id:
                    exclude_time = (
                        route.start_time.astimezone(tz) - timedelta(hours=1),
                        route.end_time.astimezone(tz) + timedelta(hours=1)
                    )
                    message_detail = (route, route.optimisation)
                    exclude_periods.append((exclude_time, 'exclude_time', message_detail))

        for exclude_time, message_code, message_detail in exclude_periods:
            new_periods = []
            for period in driver_period:
                if period[0] <= exclude_time[0] and period[1] >= exclude_time[1]:
                    new_periods.append((period[0], exclude_time[0]))
                    new_periods.append((exclude_time[1], period[1]))
                    messages.append((message_code, exclude_time[0], exclude_time[1], *message_detail))
                elif period[0] <= exclude_time[0] and period[1] <= exclude_time[1]:
                    new_periods.append((period[0], exclude_time[0]))
                    messages.append((message_code, exclude_time[0], period[1], *message_detail))
                elif period[0] >= exclude_time[0] and period[1] >= exclude_time[1]:
                    new_periods.append((exclude_time[1], period[1]))
                    messages.append((message_code, period[0], exclude_time[1], *message_detail))
                else:
                    messages.append((message_code, period[0], period[1], *message_detail))
            driver_period = new_periods

        if not driver_period:
            return None, messages

        driver_period.sort(key=lambda x: x[0] - x[1])
        return driver_period[0], messages

    def _process_by_driver_breaks(self, driver_wh, driver):
        messages = []
        if driver.schedule is None:
            return driver_wh, messages
        one_time = driver.schedule.schedule['one_time'].get(self.optimisation.day, None)
        if one_time is None:
            return driver_wh, messages
        breaks = one_time.get('breaks', [])
        for driver_break in breaks:
            start, end = driver_break['start'], driver_break['end']
            if start <= driver_wh[0].time() <= driver_wh[1].time() <= end:
                messages.append(('driver_break_exclude', start, end))
                return None, messages
            elif start <= driver_wh[0].time() <= end <= driver_wh[1].time():
                messages.append(('driver_break_lower', end, start, end))
                driver_wh[0] = driver_wh[0].replace(hour=end.hour, minute=end.minute)
            elif driver_wh[0].time() <= start <= driver_wh[1].time() <= end:
                messages.append(('driver_break_upper', start, start, end))
                driver_wh[1] = driver_wh[1].replace(hour=start.hour, minute=start.minute)
        return driver_wh, messages

    def _process_by_ro_working_hours(self, driver_wh):
        messages = []
        ro_wh = self.options.get('working_hours')
        if not ro_wh:
            return driver_wh, messages

        if driver_wh[1].time() <= ro_wh.lower or driver_wh[0].time() >= ro_wh.upper:
            messages.append(('working_hours_exclude',))
            return None, messages

        if driver_wh[0].time() < ro_wh.lower:
            driver_wh[0] = driver_wh[0].replace(hour=ro_wh.lower.hour, minute=ro_wh.lower.minute)
            messages.append(('working_hours_lower', driver_wh[0]))

        if driver_wh[1].time() > ro_wh.upper:
            driver_wh[1] = driver_wh[1].replace(hour=ro_wh.upper.hour, minute=ro_wh.upper.minute)
            messages.append(('working_hours_upper', driver_wh[1]))

        return driver_wh, messages

    def _process_by_current_time(self, working_hours):
        min_start_from = timezone.now().astimezone(self.optimisation.merchant.timezone) + timedelta(minutes=10)

        if working_hours[1] <= min_start_from:
            return None, [('passed_end_time', working_hours[1], min_start_from)]

        if working_hours[0] < min_start_from:
            working_hours[0] = min_start_from
            return working_hours, [('passed_start_time', working_hours[0], min_start_from)]

        return working_hours, []

    def _time_to_datetime(self, t):
        return self.optimisation.merchant.timezone.localize(datetime.combine(self.optimisation.day, t))

    def _get_driver_working_hours(self, driver):
        schedule, _ = Schedule.objects.get_or_create(member_id=driver.id)
        schedule_item = schedule.get_day_schedule(self.optimisation.day)
        if schedule_item['day_off']:
            logger.info(None, extra=dict(obj=self.optimisation, event=EventType.DRIVER_NOT_AVAILABLE,
                                         event_kwargs={'driver': driver, 'code': 'no_schedule'}))
            return None, []
        period = [
            self._time_to_datetime(schedule_item['start']),
            self._time_to_datetime(schedule_item['end']),
        ]
        return period, [('initial', period[0], period[1])]


class DriverLocationFilter(FilterBase):
    key = 'drivers_ids'

    def _filter_out(self, objects):
        for driver in objects:
            start_place = self.options.get('start_place')
            if start_place == HubOptions.START_HUB.default_hub:
                if driver.starting_hub is None:
                    logger.info(None, extra=dict(obj=self.optimisation, event=EventType.DRIVER_NOT_AVAILABLE,
                                                 event_kwargs={'driver': driver, 'code': 'start_hub'}))
                    yield driver
                    continue
                driver.start_point = driver.starting_hub
            elif start_place == HubOptions.START_HUB.default_point:
                if driver.ending_point is None:
                    logger.info(None, extra=dict(obj=self.optimisation, event=EventType.DRIVER_NOT_AVAILABLE,
                                                 event_kwargs={'driver': driver, 'code': 'start_point'}))
                    yield driver
                    continue
                # driver's ending_point is considered the default point for either start/end of route
                driver.start_point = {
                    'location': driver.ending_point.location,
                    'address': driver.ending_point.address
                }
            elif start_place == HubOptions.START_HUB.hub_location:
                driver.start_point = self.options.get('start_hub')
            elif start_place == HubOptions.START_HUB.driver_location:
                driver.start_point = self.options.get('start_location')
            else:
                driver.start_point = None

            end_place = self.options.get('end_place')
            if end_place == HubOptions.END_HUB.default_hub:
                if driver.ending_hub is None:
                    logger.info(None, extra=dict(obj=self.optimisation, event=EventType.DRIVER_NOT_AVAILABLE,
                                                 event_kwargs={'driver': driver, 'code': 'end_hub'}))
                    yield driver
                    continue
                driver.end_point = driver.ending_hub
            elif end_place == HubOptions.END_HUB.default_point:
                if driver.ending_point is None:
                    logger.info(None, extra=dict(obj=self.optimisation, event=EventType.DRIVER_NOT_AVAILABLE,
                                                 event_kwargs={'driver': driver, 'code': 'end_point'}))
                    yield driver
                    continue
                driver.end_point = {
                    'location': driver.ending_point.location,
                    'address': driver.ending_point.address
                }
            elif end_place == HubOptions.END_HUB.hub_location:
                driver.end_point = self.options.get('end_hub')
            elif end_place == HubOptions.END_HUB.driver_location:
                driver.end_point = self.options.get('end_location')
            else:
                driver.end_point = None


class AssignedDriverNotAvailable(FilterBase):
    key = 'jobs_ids'

    def _filter_out(self, jobs):
        drivers_ids = list(map(lambda dr: dr.id, self.options['drivers_ids']))
        return [job for job in jobs if job.status == OrderStatus.ASSIGNED and job.driver_id not in drivers_ids]

    def _process_filtered_out(self, objects):
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.JOB_FILTERED,
                                     event_kwargs={'jobs': objects, 'code': 'driver_not_available'}))


class JobDeadlineMissDriverSchedule(FilterBase):
    key = 'jobs_ids'

    def _filter_out(self, jobs):
        drivers_periods = []
        for driver in self.options['drivers_ids']:
            if not hasattr(driver, 'allowed_period'):
                continue
            drivers_periods.append((driver.id, getattr(driver, 'allowed_period')))
        if not drivers_periods:
            return []
        for job in jobs:
            good_driver = False
            for driver_id, (lower, upper) in drivers_periods:
                bad_driver_statement = job.deliver_before < lower \
                                       or (job.deliver_after and job.deliver_after > upper) \
                                       or (job.status == OrderStatus.ASSIGNED and job.driver_id != driver_id)
                if bad_driver_statement:
                    continue
                good_driver = True
                break
            if not good_driver:
                yield job

    def _process_filtered_out(self, objects):
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.JOB_FILTERED,
                                     event_kwargs={'jobs': objects, 'code': 'miss_drivers_schedule'}))


class ReOptimiseAssigned(PipeBase):
    def __call__(self):
        if not self.options['re_optimise_assigned']:
            return
        new_objects = self._find_new_objects()
        objects = self.options.pop('jobs_ids', [])
        objects.extend(new_objects)
        self.options['jobs_ids'] = objects
        if new_objects:
            self._process_new_objects(new_objects)

    def _find_new_objects(self):
        drivers_ids = list(map(lambda dr: dr.id, self.options['drivers_ids']))
        start_period, end_period = self.context['optimisation'].min_max_day_period
        qs = Order.aggregated_objects.filter_by_merchant(self.context['optimisation'].merchant)
        return list(
            qs.filter(
                driver_id__in=drivers_ids, status=OrderStatus.ASSIGNED,
                deliver_before__gt=start_period, deliver_before__lt=end_period,
            ).filter(
                Q(deliver_after__isnull=True) | Q(deliver_after__lt=end_period)
            ).exclude(id__in=list(map(attrgetter('id'), self.options.get('jobs_ids', []))))
        )

    def _process_new_objects(self, objects):
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.JOB_ADDED,
                                     event_kwargs={'jobs': objects, 'code': 're_optimise_assigned'}))


class JobStatusFilter(FilterBase):
    key = 'jobs_ids'

    def _filter_out(self, jobs):
        statuses = [OrderStatus.NOT_ASSIGNED, OrderStatus.ASSIGNED]
        return [job for job in jobs if job.status not in statuses]

    def _process_filtered_out(self, filtered_jobs):
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.JOB_FILTERED,
                                     event_kwargs={'jobs': filtered_jobs, 'code': 'status'}))


class JobSkillSetFilter(FilterBase):
    key = 'jobs_ids'

    def _filter_out(self, jobs):
        skill_sets = set()
        for driver in self.options['drivers_ids']:
            skill_sets.add(tuple(sk.id for sk in driver.skill_sets.all()))
        if len(skill_sets) == 0:
            return
        for job in jobs:
            job_skill = set(sk.id for sk in job.skill_sets.all())
            job_skill_satisfied = [1 for driver_skill in skill_sets if not job_skill.difference(driver_skill)]
            if not job_skill_satisfied:
                yield job

    def _process_filtered_out(self, filtered_jobs):
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.JOB_FILTERED,
                                     event_kwargs={'jobs': filtered_jobs, 'code': 'skill_set'}))


class DriverSkillSetFilter(FilterBase):
    key = 'drivers_ids'

    def _filter_out(self, drivers):
        skill_sets = set()
        for job in self.options['jobs_ids']:
            skill_sets.add(tuple(sk.id for sk in job.skill_sets.all()))
        if len(skill_sets) == 0:
            return
        for driver in drivers:
            driver_skill = set(sk.id for sk in driver.skill_sets.all())
            job_skill_satisfied = [1 for job_skill in skill_sets if not set(job_skill).difference(driver_skill)]
            if not job_skill_satisfied:
                yield driver

    def _process_filtered_out(self, filtered_drivers):
        for driver in filtered_drivers:
            logger.info(None, extra=dict(obj=self.optimisation, event=EventType.DRIVER_NOT_AVAILABLE,
                                         event_kwargs={'driver': driver, 'code': 'skill_set'}))


class JobDayFilter(FilterBase):
    key = 'jobs_ids'

    def _prepare(self):
        tz = self.optimisation.merchant.timezone
        self.day_start = tz.localize(datetime.combine(self.optimisation.day, datetime.min.time()))
        self.day_end = tz.localize(datetime.combine(self.optimisation.day, datetime.max.time()))

    def _filter_out(self, jobs):
        for job in jobs:
            if job.deliver_after and job.deliver_after > self.day_end:
                yield job
            elif job.deliver_before < self.day_start:
                yield job

    def _process_filtered_out(self, filtered_jobs):
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.JOB_FILTERED,
                                     event_kwargs={'jobs': filtered_jobs, 'code': 'wrong_day'}))


class JobWorkingHoursFilter(FilterBase):
    key = 'jobs_ids'

    def _filter_out(self, jobs):
        working_hours = self.options.get('working_hours')
        tz = self.optimisation.merchant.timezone
        for job in jobs:
            if job.deliver_after and job.deliver_after.astimezone(tz).time() > working_hours.upper:
                yield job
            elif job.deliver_before.astimezone(tz).time() < working_hours.lower:
                yield job

    def _process_filtered_out(self, filtered_jobs):
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.JOB_FILTERED,
                                     event_kwargs={'jobs': filtered_jobs, 'code': 'working_hours'}))

    def _active(self):
        return bool(self.options.get('working_hours'))


class JobIntersectsOtherOptimisationFilter(FilterBase):
    key = 'jobs_ids'

    def _prepare(self):
        self.used_jobs = set()

        for optimisation in self.context[CONTEXT_HELP_ITEM].get('in_process_optimisations', []):
            if not optimisation.optimisation_options:
                continue
            self.used_jobs |= {job['id'] for job in optimisation.optimisation_options['jobs']}

        for optimisation in self.context[CONTEXT_HELP_ITEM].get('day_optimisations', []):
            for route in optimisation.routes.all():
                for point in route.points.all():
                    if point.point_content_type == ContentType.objects.get_for_model(Order):
                        self.used_jobs.add(point.point_object_id)

    def _filter_out(self, jobs):
        return [job for job in jobs if job.id in self.used_jobs]

    def _process_filtered_out(self, filtered_jobs):
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.JOB_FILTERED,
                                     event_kwargs={'jobs': filtered_jobs, 'code': 'other_optimisations'}))
