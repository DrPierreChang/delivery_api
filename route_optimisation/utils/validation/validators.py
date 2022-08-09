import copy
import logging
from operator import itemgetter

from django.utils.translation import ugettext_lazy as _

from route_optimisation.const import CONTEXT_HELP_ITEM, MAX_JOBS_COUNT
from route_optimisation.exceptions import OptimisationValidError
from route_optimisation.logging import EventType
from route_optimisation.models import RouteOptimisation
from route_optimisation.utils.validation.filters import (
    AssignedDriverNotAvailable,
    DriverLocationFilter,
    DriverSkillSetFilter,
    DriverTimeFilter,
    JobDayFilter,
    JobDeadlineMissDriverSchedule,
    JobIntersectsOtherOptimisationFilter,
    JobSkillSetFilter,
    JobStatusFilter,
    JobWorkingHoursFilter,
    ReOptimiseAssigned,
)
from route_optimisation.utils.validation.options_serializers import (
    MoveOrdersExistingOptimisationOptionsSerializer,
    MoveOrdersOptimisationOptionsSerializer,
    OptimisationOptionsSerializer,
    RefreshOptimisationOptionsSerializer,
)
from route_optimisation.utils.validation.serializers import (
    AdvancedRouteOptimisationValidateOptionsSerializer,
    MoveOrdersValidateOptionsSerializer,
    RefreshAdvancedRouteOptimisationValidateOptionsSerializer,
    RefreshSoloRouteOptimisationValidateOptionsSerializer,
    SoloRouteOptimisationValidateOptionsSerializer,
)

logger = logging.getLogger('optimisation')


class JobCount:
    def __call__(self, optimisation, options, final_options, context):
        count = len(options.get('jobs_ids', []))
        if count == 0:
            logger.info(None, extra=dict(obj=optimisation, event=EventType.VALIDATION_ERROR,
                                         event_kwargs={'code': 'no_jobs'}))
            raise OptimisationValidError(_('There are no jobs to optimise'))
        if count > MAX_JOBS_COUNT:
            logger.info(None, extra=dict(obj=optimisation, event=EventType.VALIDATION_ERROR,
                                         event_kwargs={'code': 'many_jobs',
                                                       'count': count,
                                                       'max_count': MAX_JOBS_COUNT}))
            raise OptimisationValidError(_('Too many jobs to optimise'))


class DriverCount:
    def __call__(self, optimisation, options, final_options, context):
        if len(options.get('drivers_ids', [])) == 0:
            logger.info(None, extra=dict(obj=optimisation, event=EventType.VALIDATION_ERROR,
                                         event_kwargs={'code': 'no_drivers'}))
            raise OptimisationValidError(_('There are no drivers available'))


class RefreshOptionsChanged:
    def __call__(self, optimisation, options, final_options, context):
        source_optimisation = optimisation.source_optimisation
        last_options = None
        for log_item in source_optimisation.optimisation_log.log['full']:
            if log_item.get('event') == EventType.REFRESH_OPTIONS:
                last_options = log_item['params']['optimisation_options']
        last_options = last_options or source_optimisation.optimisation_options

        if self._check_equality(final_options, last_options):
            logger.info(None, extra=dict(obj=optimisation, event=EventType.VALIDATION_ERROR,
                                         event_kwargs={'code': 'refresh_options_equals'}))
            raise OptimisationValidError('Nothing to refresh. Everything is already optimised')

    def _check_equality(self, new_options, old_options):
        new_options = self._clean_options(new_options)
        old_options = self._clean_options(old_options)
        return new_options == old_options

    def _clean_options(self, options):
        # Get rid of not needed fields
        options = copy.deepcopy(options)
        if 'required_start_sequence' in options:
            del options['required_start_sequence']
        for job in options['jobs']:
            if 'allow_skip' in job:
                del job['allow_skip']
        options['jobs'].sort(key=itemgetter('id'))
        options['drivers'].sort(key=itemgetter('id'))
        return options


class ValidationMaster:
    serializer_class = None
    final_serializer_class = OptimisationOptionsSerializer
    pipes = []
    validators = []

    def __init__(self, optimisation):
        self.optimisation = optimisation

    def validate(self, options, serializer_context):
        optimisation_options = {}
        try:
            optimisation_options = self._validate(options, serializer_context)
        except OptimisationValidError as exc:
            self.optimisation.backend.on_fail(exception=exc,
                                              ignore_push_to_driver=serializer_context.get('no_sync_push', False))
            self.optimisation.delayed_task.complete()
            self.optimisation.delayed_task.save(update_fields=('status',))
        finally:
            self.optimisation.refresh_from_db()
            self.optimisation.options = options
            self.optimisation.optimisation_options = optimisation_options
            self.optimisation.save(update_fields=('options', 'optimisation_options',))

    def _validate(self, options, serializer_context):
        context = dict(optimisation=self.optimisation, **serializer_context)

        serializer = self.serializer_class(data=copy.deepcopy(options), context=context)
        serializer.is_valid(raise_exception=True)
        valid_options = serializer.validated_data

        context[CONTEXT_HELP_ITEM] = self._context_data(self.optimisation, valid_options)
        for filter_class in self.pipes:
            filter_obj = filter_class(self.optimisation, valid_options, context)
            filter_obj()
        final_options = self.final_serializer_class(valid_options, context=context).data
        for validator in self.validators:
            validator(self.optimisation, valid_options, final_options, context)
        return final_options

    def _context_data(self, optimisation, valid_options):
        states = RouteOptimisation.STATE

        day_optimisations = list(
            RouteOptimisation.objects
                .filter(day=optimisation.day)
                .exclude(id=optimisation.id)
                .exclude(state__in=(states.REMOVED, states.FAILED, states.FINISHED))
                .prefetch_related('routes__points__point_object')
        )

        in_process_optimisations = [
            optimisation for optimisation in day_optimisations
            if optimisation.state in (states.CREATED, states.VALIDATION, states.OPTIMISING)
        ]

        return {
            'day_optimisations': day_optimisations,
            'in_process_optimisations': in_process_optimisations,
        }


class SoloOptions(ValidationMaster):
    serializer_class = SoloRouteOptimisationValidateOptionsSerializer
    pipes = [
        JobStatusFilter,
        JobDayFilter,
        ReOptimiseAssigned,
        JobSkillSetFilter,
        DriverSkillSetFilter,
        DriverTimeFilter,
        DriverLocationFilter,
        JobIntersectsOtherOptimisationFilter,
        JobDeadlineMissDriverSchedule,
    ]
    validators = [
        JobCount(),
        DriverCount(),
    ]


class AdvancedOptions(ValidationMaster):
    serializer_class = AdvancedRouteOptimisationValidateOptionsSerializer
    pipes = [
        JobStatusFilter,
        JobDayFilter,
        ReOptimiseAssigned,
        JobWorkingHoursFilter,
        JobSkillSetFilter,
        DriverSkillSetFilter,
        DriverTimeFilter,
        DriverLocationFilter,
        AssignedDriverNotAvailable,
        JobIntersectsOtherOptimisationFilter,
        JobDeadlineMissDriverSchedule,
    ]
    validators = [
        JobCount(),
        DriverCount(),
    ]


class MoveOrdersValidationMaster:
    serializer_class = None
    final_serializer_class = None
    pipes = []
    validators = []

    def __init__(self, dummy_optimisation):
        self.dummy_optimisation = dummy_optimisation

    def validate(self, options, serializer_context):
        optimisation_options = {}
        try:
            optimisation_options = self._validate(options, serializer_context)
        except OptimisationValidError as exc:
            self.dummy_optimisation.backend.on_fail(
                exception=exc, ignore_push_to_driver=serializer_context.get('no_sync_push', False)
            )
        finally:
            self.dummy_optimisation.options = options
            self.dummy_optimisation.optimisation_options = optimisation_options

    def _validate(self, options, serializer_context):
        context = dict(optimisation=self.dummy_optimisation, **serializer_context)

        serializer = self.serializer_class(data=copy.deepcopy(options), context=context)
        serializer.is_valid(raise_exception=True)
        valid_options = serializer.validated_data

        context[CONTEXT_HELP_ITEM] = self._context_data()
        for filter_class in self.pipes:
            filter_obj = filter_class(self.dummy_optimisation, valid_options, context)
            filter_obj()
        final_options = self.final_serializer_class(valid_options, context=context).data
        for validator in self.validators:
            validator(self.dummy_optimisation, valid_options, final_options, context)
        return final_options

    def _context_data(self):
        states = RouteOptimisation.STATE

        day_optimisations = list(
            RouteOptimisation.objects
                .filter(day=self.dummy_optimisation.source_optimisation.day)
                .exclude(id=self.dummy_optimisation.source_optimisation.id)
                .exclude(state__in=(states.REMOVED, states.FAILED, states.FINISHED))
                .prefetch_related('routes__points__point_object')
        )

        in_process_optimisations = [
            optimisation for optimisation in day_optimisations
            if optimisation.state in (states.CREATED, states.VALIDATION, states.OPTIMISING)
        ]

        return {
            'day_optimisations': day_optimisations,
            'in_process_optimisations': in_process_optimisations,
            'source_optimisation': self.dummy_optimisation.source_optimisation,
        }


class SoloMoveOrdersOptions(MoveOrdersValidationMaster):
    serializer_class = MoveOrdersValidateOptionsSerializer
    final_serializer_class = MoveOrdersOptimisationOptionsSerializer
    pipes = [
        DriverTimeFilter,
        DriverLocationFilter,
    ]
    validators = [
        JobCount(),
        DriverCount(),
    ]


class AdvancedMoveOrdersOptions(MoveOrdersValidationMaster):
    serializer_class = MoveOrdersValidateOptionsSerializer
    final_serializer_class = MoveOrdersExistingOptimisationOptionsSerializer
    pipes = [
        DriverTimeFilter,
        DriverLocationFilter,
    ]
    validators = [
        JobCount(),
        DriverCount(),
    ]


class RefreshDummySoloOptions(MoveOrdersValidationMaster):
    serializer_class = RefreshSoloRouteOptimisationValidateOptionsSerializer
    final_serializer_class = RefreshOptimisationOptionsSerializer
    pipes = [
        JobDayFilter,
        ReOptimiseAssigned,
        JobSkillSetFilter,
        DriverSkillSetFilter,
        DriverTimeFilter,
        DriverLocationFilter,
        JobIntersectsOtherOptimisationFilter,
        JobDeadlineMissDriverSchedule,
    ]
    validators = [
        JobCount(),
        DriverCount(),
        RefreshOptionsChanged(),
    ]


class RefreshDummyAdvancedOptions(MoveOrdersValidationMaster):
    serializer_class = RefreshAdvancedRouteOptimisationValidateOptionsSerializer
    final_serializer_class = RefreshOptimisationOptionsSerializer
    pipes = [
        JobDayFilter,
        ReOptimiseAssigned,
        JobSkillSetFilter,
        DriverSkillSetFilter,
        DriverTimeFilter,
        DriverLocationFilter,
        JobIntersectsOtherOptimisationFilter,
        JobDeadlineMissDriverSchedule,
    ]
    validators = [
        JobCount(),
        DriverCount(),
        RefreshOptionsChanged(),
    ]
