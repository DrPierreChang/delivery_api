import logging
import threading
from typing import List, Optional

logger = logging.getLogger('optimisation')


class EventHandler:
    def dev(self, event: str, msg: Optional[str], append_labels: List[str] = None, **kwargs):
        pass

    def dev_msg(self, msg: str, append_labels: List[str] = None, **kwargs):
        pass

    def msg(self, msg: str, append_labels: List[str] = None, **kwargs):
        pass

    def info(self, event: str, msg: Optional[str], append_labels: List[str] = None, **kwargs):
        pass

    def progress(self, **kwargs):
        pass

    def error(self, error_msg):
        logger.debug('EH ERROR %s' % error_msg)


class set_event_handler:
    def __init__(self, handler):
        self.handler = handler

    def __enter__(self):
        event_handler.set_handler(self.handler)

    def __exit__(self, exc_type, exc_val, exc_tb):
        event_handler.set_handler(None)


class CurrentEventHandlerKeeper(threading.local):
    def __init__(self):
        self._handler = None

    def set_handler(self, value):
        self._handler = value

    def get_handler(self):
        return self._handler

    def __getattr__(self, item):
        assert self._handler is not None, 'No Event Handler set'
        assert hasattr(self._handler, item), 'Event Handler have no "%s" attribute' % item
        return getattr(self._handler, item)


event_handler = CurrentEventHandlerKeeper()
