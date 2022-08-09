import logging

from django.db import transaction

import sentry_sdk
from celery.exceptions import SoftTimeLimitExceeded

from route_optimisation.engine import EngineParameters, ROError
from route_optimisation.engine.base_classes.result import AssignmentResult
from route_optimisation.exceptions import OptimisationValidError
from route_optimisation.logging import EventType
from route_optimisation.logging.logs.progress import ProgressConst
from route_optimisation.models import EngineRun, RouteOptimisation
from route_optimisation.utils.refresh_polylines import PostProcessingRefreshPolylines
from routing.context_managers import GoogleApiRequestsTracker

logger = logging.getLogger('optimisation')


class OptimisationBackend:
    options_validator_class = None
    result_keeper_class = None
    deletion_class = None
    sequence_reorder_service_class = None
    move_orders_prepare_class = None
    move_orders_save_class = None
    refresh_backend_name = None

    def __init__(self, optimisation):
        self.optimisation = optimisation
        self.sequence_reorder_service = self.sequence_reorder_service_class \
            and self.sequence_reorder_service_class(self.optimisation)

    def validate_options(self, options, serializer_context):
        self.options_validator_class(self.optimisation).validate(options, serializer_context)

    def on_create(self, *args, **kwargs):
        self.optimisation.state_to(RouteOptimisation.STATE.VALIDATION)

    def on_delete(self, initiator, unassign=False, cms_user=False):
        self.deletion_class(self.optimisation).delete(initiator, unassign, cms_user)

    def prepare_move_orders(self, *args, **kwargs):
        return self.move_orders_prepare_class(self.optimisation).prepare(*args, **kwargs)

    def on_move_orders(self, *args, **kwargs):
        return self.move_orders_save_class(self.optimisation).save(*args, **kwargs)

    def get_params_for_engine(self) -> EngineParameters:
        merchant = self.optimisation.merchant
        service_time = self.optimisation.optimisation_options.get('service_time', merchant.job_service_time)
        pickup_service_time = self.optimisation.optimisation_options.get('pickup_service_time',
                                                                         merchant.pickup_service_time)
        return EngineParameters(
            timezone=merchant.timezone,
            default_job_service_time=service_time,
            default_pickup_service_time=pickup_service_time,
            day=self.optimisation.day,
            focus=merchant.route_optimization_focus,
            optimisation_options=self.optimisation.optimisation_options
        )

    def on_finish(self, engine_result, **params):
        assert engine_result.good
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.PROGRESS,
                                     event_kwargs=dict(stage=ProgressConst.ASSIGN), labels=[], ))
        self.result_keeper_class(self.optimisation).prepare_and_save(engine_result)
        self.optimisation.state_to(RouteOptimisation.STATE.COMPLETED)

    def on_fail(self, engine_result: AssignmentResult = None, exception=None, ignore_push_to_driver=False):
        if getattr(self.optimisation, 'is_terminated', False):
            unprocessed_runs = self.optimisation.engine_runs.filter(state=EngineRun.STATE.ENGINE_CREATED)
            for engine_run in unprocessed_runs:
                engine_run.state_to(EngineRun.STATE.ENGINE_FAILED)
            return

        assert engine_result or exception
        params = {'exception_dict': engine_result.exception_dict} \
            if engine_result else {'exception_object': exception}
        self._handle_exc_on_fail(**params)
        self.optimisation.state_to(RouteOptimisation.STATE.FAILED)
        if not ignore_push_to_driver:
            self.result_keeper_class(self.optimisation).push_to_drivers(successful=False)

    def _handle_exc_on_fail(self, exception_dict=None, exception_object=None):
        assert exception_dict is not None or exception_object is not None
        exc_class = exception_dict['exc_class'] if exception_dict is not None else exception_object.__class__
        if issubclass(exc_class, OptimisationValidError):
            return
        elif issubclass(exc_class, ROError):
            logger.info(None, extra=dict(obj=self.optimisation, event=EventType.EXCEPTION,
                                         event_kwargs={'exc': exception_object, 'exc_dict': exception_dict,
                                                       'code': 'ro_error'}))
            return
        elif issubclass(exc_class, SoftTimeLimitExceeded):
            logger.info(None, extra=dict(obj=self.optimisation, event=EventType.EXCEPTION,
                                         event_kwargs={'code': 'time_limit'}))
        else:
            logger.info(None, extra=dict(obj=self.optimisation, event=EventType.EXCEPTION,
                                         event_kwargs={'exc': exception_object, 'exc_dict': exception_dict,
                                                       'code': 'unknown'}))
        if exception_object is not None:
            sentry_sdk.capture_exception(exception_object)

    def track_api_requests_stat(self, tracker: GoogleApiRequestsTracker):
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.TRACK_API_STAT,
                                     event_kwargs={'stat': tracker.stat}))
        with transaction.atomic():
            self.optimisation.refresh_from_db()
            if not self.optimisation.google_api_requests:
                self.optimisation.google_api_requests = tracker.stat
            else:
                for key, value in tracker.stat.items():
                    self.optimisation.google_api_requests[key] += value
            self.optimisation.save(update_fields=('google_api_requests',))

    def on_terminate(self, initiator):
        logger.info(None, extra=dict(obj=self.optimisation,
                                     event=EventType.TERMINATE_RO,
                                     event_kwargs={
                                         'code': 'terminated',
                                         'initiator': initiator
                                     }))
        self.optimisation.delayed_task.terminate_tasks_pool()

    def post_processing(self, engine_result, distance_matrix_cache=None, event_handler=None):
        return PostProcessingRefreshPolylines(self.optimisation).refresh_polylines(
            engine_result, distance_matrix_cache=distance_matrix_cache, event_handler=event_handler
        )
