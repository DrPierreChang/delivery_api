import logging
from typing import Optional

from django.contrib.postgres.fields import JSONField
from django.db import models

import sentry_sdk
from billiard.exceptions import SoftTimeLimitExceeded
from model_utils import Choices
from model_utils.models import TimeStampedModel

from route_optimisation.dima import RadaroDimaCache
from route_optimisation.engine import Engine, EngineParameters, ROError
from route_optimisation.logging import EventType, ROLogGetter
from route_optimisation.optimisation_events import RadaroEventsHandler
from routing.google import GoogleClient

from ..engine.base_classes.result import AssignmentResult
from ..exceptions import OptimisationValidError
from .log import ROLog

logger = logging.getLogger('optimisation')


class EngineOptions:
    def __init__(self, params: EngineParameters, algorithm, algorithm_params: dict = None):
        self.algorithm = algorithm
        self.algorithm_params = algorithm_params or {}
        self.params: EngineParameters = params

    def to_dict(self):
        return {
            'algorithm': self.algorithm,
            'algorithm_params': self.algorithm_params,
            'params': self.params.to_dict(),
        }

    @classmethod
    def from_dict(cls, options):
        return cls(EngineParameters.from_dict(options['params']), options['algorithm'], options['algorithm_params'])


class EngineOptionsField(JSONField):
    def get_prep_value(self, value) -> dict:
        if not isinstance(value, dict):
            value = value.to_dict()
        return super().get_prep_value(value)

    def from_db_value(self, value: dict, expression, connection) -> Optional[EngineOptions]:
        if not value:
            return None
        return EngineOptions.from_dict(value)


class EngineResultField(JSONField):
    def get_prep_value(self, value):
        if not isinstance(value, dict):
            value = value.to_dict()
        return super().get_prep_value(value)

    def from_db_value(self, value, expression, connection) -> Optional[AssignmentResult]:
        if not value:
            return None
        return AssignmentResult.from_dict(value)


class EngineRun(TimeStampedModel, ROLogGetter, models.Model):
    STATE = Choices(
        ('ENGINE_CREATED', 'Created'),
        ('ENGINE_OPTIMISING', 'Optimising'),
        ('ENGINE_COMPLETED', 'Completed'),
        ('ENGINE_FAILED', 'Failed'),
    )
    calculating = (STATE.ENGINE_CREATED, STATE.ENGINE_OPTIMISING)
    calculated = (STATE.ENGINE_COMPLETED, STATE.ENGINE_FAILED)
    state = models.CharField(max_length=20, choices=STATE, default=STATE.ENGINE_CREATED)

    optimisation = models.ForeignKey('route_optimisation.RouteOptimisation', on_delete=models.CASCADE,
                                     related_name='engine_runs')
    engine_log = models.ForeignKey('route_optimisation.ROLog', on_delete=models.PROTECT)

    engine_options = EngineOptionsField(default=dict, blank=True)
    result = EngineResultField(default=dict, blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dummy_optimisation = None

    @property
    def dummy_optimisation(self):
        return self._dummy_optimisation

    @dummy_optimisation.setter
    def dummy_optimisation(self, value):
        self._dummy_optimisation = value

    @property
    def active_optimisation_obj(self):
        return self.dummy_optimisation or self.optimisation

    def save(self, *args, **kwargs):
        exists = bool(self.id)
        if not exists and not hasattr(self, 'engine_log'):
            self.engine_log = ROLog.objects.create()
        super().save(*args, **kwargs)
        if not exists:
            logger.info(None, extra=dict(obj=self, event=EventType.RO_STATE_CHANGE, event_kwargs={'state': self.state}))

    def state_to(self, state):
        logger.info(None, extra=dict(obj=self, event=EventType.RO_STATE_CHANGE, event_kwargs={'state': state}))
        self.state = state
        self.save(update_fields=('state',))

    @property
    def get_ro_log(self) -> ROLog:
        return self.engine_log

    def run_engine(self, dima_cache=None):
        self.refresh_from_db()
        engine_params = self.engine_options.params
        engine_algorithm = self.engine_options.algorithm
        engine_algorithm_params = self.engine_options.algorithm_params
        engine = Engine(
            algorithm=engine_algorithm,
            event_handler=RadaroEventsHandler(self),
            distance_matrix_cache=dima_cache or RadaroDimaCache(),
            algorithm_params=engine_algorithm_params,
        )
        self.state_to(EngineRun.STATE.ENGINE_OPTIMISING)
        try:
            with GoogleClient.track_merchant(self.optimisation.merchant):
                result = engine.run(params=engine_params)
            self.on_finish(result)
        except Exception as exc:
            self.on_error(exc)
        finally:
            self.optimisation.backend.track_api_requests_stat(engine.api_requests_tracker)
        return self.result

    def on_finish(self, result: AssignmentResult):
        self.result = result
        self.save(update_fields=('result',))
        self.state_to(self.STATE.ENGINE_COMPLETED)

    def on_error(self, exc):
        self.result = AssignmentResult.failed_assignment(exc)
        self.save(update_fields=('result',))
        self.state_to(self.STATE.ENGINE_FAILED)
        self._handle_exc_on_fail(exc)

    def _handle_exc_on_fail(self, exc):
        if isinstance(exc, SoftTimeLimitExceeded):
            logger.info(None, extra=dict(obj=self, event=EventType.EXCEPTION,
                                         event_kwargs={'code': 'time_limit'}))
            sentry_sdk.capture_exception(exc)
        elif isinstance(exc, OptimisationValidError):
            pass
        elif isinstance(exc, ROError):
            logger.info(None, extra=dict(obj=self, event=EventType.EXCEPTION,
                                         event_kwargs={'exc': exc, 'code': 'ro_error'}))
        else:
            logger.info(None, extra=dict(obj=self, event=EventType.EXCEPTION,
                                         event_kwargs={'exc': exc, 'code': 'unknown'}))
            sentry_sdk.capture_exception(exc)
