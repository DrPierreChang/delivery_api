import logging

from django.utils.translation import ugettext_lazy as _

import sentry_sdk

from route_optimisation.exceptions import MoveOrdersError, OptimisationValidError
from route_optimisation.logging import EventType
from route_optimisation.utils.managing import MoveOrdersType
from route_optimisation.utils.results import (
    ExistingRouteOptimiseResultKeeper,
    NewAdvancedRouteOptimiseResultKeeper,
    NewRouteOptimiseResultKeeper,
)
from route_optimisation.utils.validation.validators import AdvancedMoveOrdersOptions, SoloMoveOrdersOptions
from routing.context_managers import GoogleApiRequestsTracker

from ...engine import ROError
from ...engine.base_classes.result import AssignmentResult
from ...models import RouteOptimisation
from .base import OptimisationBackend
from .registry import backend_registry

logger = logging.getLogger('optimisation')


class DummyOptimisationBackendBase(OptimisationBackend):
    def on_create(self, options=None, serializer_context=None):
        options = options or {}
        serializer_context = serializer_context or {}
        self.validate_options(options, serializer_context)

    def on_finish(self, engine_result, **params):
        assert engine_result.good
        self.optimisation.state_to(RouteOptimisation.STATE.COMPLETED)
        prepared_optimisation_result = self.result_keeper_class(self.optimisation).prepare(engine_result, **params)
        prepared_route_info = prepared_optimisation_result.routes[0]
        return prepared_route_info.route, prepared_route_info.points

    def on_fail(self, engine_result: AssignmentResult = None, exception=None, *args, **kwargs):
        self.optimisation.state_to(RouteOptimisation.STATE.FAILED)
        assert engine_result or exception
        params = {'exception_dict': engine_result.exception_dict} \
            if engine_result else {'exception_object': exception}
        self._handle_exc_on_fail(**params)

    def _handle_exc_on_fail(self, exception_dict=None, exception_object=None):
        assert exception_dict is not None or exception_object is not None
        exc_class = exception_dict['exc_class'] if exception_dict is not None else exception_object.__class__
        if issubclass(exc_class, OptimisationValidError):
            self._handle_optimisation_valid_error(self.optimisation)
            return
        elif issubclass(exc_class, ROError):
            logger.info(None, extra=dict(obj=self.optimisation, event=EventType.EXCEPTION,
                                         event_kwargs={'exc': exception_object, 'exc_dict': exception_dict,
                                                       'code': 'ro_error'}))
            return
        if exception_object:
            logger.info(None, extra=dict(obj=self.optimisation, event=EventType.EXCEPTION,
                                         event_kwargs={'exc': exception_object, 'code': 'unknown'}))
            sentry_sdk.capture_exception(exception_object)
            raise MoveOrdersError('Can not move orders. Unexpected error occurred.')

    def track_api_requests_stat(self, tracker: GoogleApiRequestsTracker):
        raise NotImplementedError()

    @staticmethod
    def _handle_optimisation_valid_error(dummy_optimisation):
        last_log = dummy_optimisation.optimisation_log.log['full'][-1]
        message = ''
        if last_log['event'] == EventType.VALIDATION_ERROR and last_log['params']['code'] == 'no_drivers':
            for log_item in dummy_optimisation.optimisation_log.log['full']:
                text = None
                if log_item.get('event') == EventType.DRIVER_NOT_AVAILABLE:
                    driver_full_name = log_item['params']['driver_full_name']
                    code = log_item['params']['code']
                    if code in ('start_hub', 'end_hub'):
                        text = 'Driver {} hasn\'t set a default hub.' .format(driver_full_name)
                    elif code == 'no_schedule':
                        text = 'Driver {} is unavailable during the working hours.' \
                            .format(driver_full_name, _('Optimisation'))
                elif log_item.get('event') == EventType.DRIVER_TIME:
                    driver_full_name = log_item['params']['driver_full_name']
                    messages = log_item['params']['messages']
                    for code, *other in messages:
                        if code == 'no_time':
                            text = 'Driver {} is unavailable during the {} working hours.' \
                                .format(driver_full_name, _('Optimisation'))
                if text:
                    message += text
        message = message or 'Can not place new orders in target drivers route'
        raise MoveOrdersError(message)


@backend_registry.register(MoveOrdersType.NEW_SOLO)
class NewRouteOptimiseBackend(DummyOptimisationBackendBase):
    options_validator_class = SoloMoveOrdersOptions
    result_keeper_class = NewRouteOptimiseResultKeeper


@backend_registry.register(MoveOrdersType.NEW_ADVANCED)
class NewAdvancedRouteOptimisationBackend(DummyOptimisationBackendBase):
    options_validator_class = SoloMoveOrdersOptions
    result_keeper_class = NewAdvancedRouteOptimiseResultKeeper


@backend_registry.register(MoveOrdersType.EXISTING_ADVANCED)
class ExistingRouteOptimiseBackend(DummyOptimisationBackendBase):
    options_validator_class = AdvancedMoveOrdersOptions
    result_keeper_class = ExistingRouteOptimiseResultKeeper
