from ..const import EventType
from ..registry import log_item_registry
from .base import LogItem


@log_item_registry.register()
class OrToolsContextLog(LogItem):
    event = EventType.CONTEXT_BUILDING

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        return '[Context] %s' % item['params']['msg']


@log_item_registry.register()
class OptimisationProcessLog(LogItem):
    event = EventType.OPTIMISATION_PROCESS

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        return item['params']['msg']
