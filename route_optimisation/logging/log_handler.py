import logging
from typing import Type

from django.db import transaction

from .const import EventLabel, EventType
from .logs.base import LogItem
from .registry import log_item_registry


class ROLogGetter:
    @property
    def get_ro_log(self):  # -> ROLog
        raise NotImplementedError()


class Writer:
    @staticmethod
    def write(log_item, ro_log, labels):
        raise NotImplementedError()


class BaseLogHandler(logging.Handler):
    writer = None

    def emit(self, record):
        event = getattr(record, 'event', EventType.SIMPLE_MESSAGE)
        log_class: Type[LogItem] = log_item_registry.get(event)
        assert log_class, 'Log handler for `{}` event type is not defined'.format(event)
        log_subject: ROLogGetter = record.obj
        log_item = log_class(msg=record.msg, event_kwargs=getattr(record, 'event_kwargs', {}), log_subject=log_subject)
        self.writer.write(log_item, log_subject.get_ro_log, getattr(record, 'labels', None) or [])


class OptimisationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        from route_optimisation.models import EngineRun, RouteOptimisation
        return isinstance(record.obj, (RouteOptimisation, EngineRun))


class DataBaseLogWriter(Writer):
    @staticmethod
    def write(log_item, ro_log, labels):
        with transaction.atomic():
            ro_log.refresh_from_db()
            log_item.write_in_log(ro_log.log, labels)
            ro_log.save(update_fields=('log',))


class OptimisationLogHandler(BaseLogHandler):
    writer = DataBaseLogWriter


class DummyOptimisationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        from route_optimisation.models import DummyOptimisation
        return isinstance(record.obj, DummyOptimisation)


class DummyOptimisationWriter(Writer):
    @staticmethod
    def write(log_item, ro_log, labels):
        log_item.write_in_log(ro_log.log, labels)


class DummyOptimisationLogHandler(BaseLogHandler):
    writer = DummyOptimisationWriter


def move_dummy_optimisation_log(dummy_optimisation, route_optimisation, dev=True):
    route_optimisation.optimisation_log.refresh_from_db()
    for log in dummy_optimisation.optimisation_log.log['full']:
        if dev and EventLabel.DEV not in log['labels']:
            log['labels'].append(EventLabel.DEV)
        if 'full' in route_optimisation.optimisation_log.log:
            route_optimisation.optimisation_log.log['full'] += [log]
        else:
            route_optimisation.optimisation_log.log['full'] = [log]
    dummy_optimisation.optimisation_log.log['full'] = []
    route_optimisation.optimisation_log.save(update_fields=('log',))
