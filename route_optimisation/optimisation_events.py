import logging
from typing import List, Optional

from .engine.events import EventHandler
from .logging import EventLabel, EventType

logger = logging.getLogger('optimisation')


class RadaroEventsHandler(EventHandler):
    EVENT_START = 'Start'

    def __init__(self, log_object):
        super().__init__()
        self.log_object = log_object

    def dev(self, event: str, msg: Optional[str], append_labels: List[str] = None, **kwargs):
        logger.info(
            msg,
            extra=dict(
                obj=self.log_object,
                event=event,
                event_kwargs=kwargs,
                labels=[EventLabel.DEV] + (append_labels or []),
            )
        )

    def dev_msg(self, msg: str, append_labels: List[str] = None, **kwargs):
        logger.info(
            msg,
            extra=dict(
                obj=self.log_object,
                event=EventType.SIMPLE_MESSAGE,
                event_kwargs=kwargs,
                labels=[EventLabel.DEV] + (append_labels or []),
            )
        )

    def msg(self, msg: str, append_labels: List[str] = None, **kwargs):
        logger.info(
            msg,
            extra=dict(
                obj=self.log_object,
                event=EventType.SIMPLE_MESSAGE,
                event_kwargs=kwargs,
                labels=(append_labels or []),
            )
        )

    def info(self, event: str, msg: Optional[str], append_labels: List[str] = None, optimisation_propagate=False, **kwargs):
        logger.info(
            msg,
            extra=dict(
                obj=self.log_object,
                event=event,
                event_kwargs=kwargs,
                labels=(append_labels or []),
            )
        )
        from route_optimisation.models import EngineRun
        if optimisation_propagate and isinstance(self.log_object, EngineRun):
            logger.info(
                msg,
                extra=dict(
                    obj=self.log_object.active_optimisation_obj,
                    event=event,
                    event_kwargs=kwargs,
                    labels=(append_labels or []),
                )
            )

    def progress(self, **kwargs):
        logger.info(None, extra=dict(obj=self.log_object, event=EventType.PROGRESS,
                                     event_kwargs=kwargs, labels=[],))
        from route_optimisation.models import EngineRun
        if isinstance(self.log_object, EngineRun):
            kwargs['engine_run_state'] = {
                'engine_id': self.log_object.id,
                'progress': self.log_object.get_ro_log.log['progress'],
            }
            logger.info(None, extra=dict(obj=self.log_object.active_optimisation_obj, event=EventType.PROGRESS,
                                         event_kwargs=kwargs, labels=[],))

    def error(self, error_msg):
        logger.info(
            error_msg,
            extra=dict(
                obj=self.log_object,
                event=EventType.SIMPLE_MESSAGE,
                event_kwargs={},
                labels=[EventLabel.DEV, EventLabel.ERROR],
            )
        )
