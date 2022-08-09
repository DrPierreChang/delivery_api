import contextlib
from functools import wraps

import mock


class NotificationTestMixin(object):
    push_available_func_path = 'notification.models.mixins.SendNotificationMixin.push_available'
    send_push_func_path = 'notification.models.mixins.SendNotificationMixin.send_versioned_push'

    @classmethod
    def make_push_available(cls, func):
        @wraps(func)
        def patched(*args, **kwargs):
            with mock.patch(cls.push_available_func_path) as push_available_func_mock:
                push_available_func_mock.return_value = True
                result = func(*args, **kwargs)
                return result
        return patched

    @classmethod
    @contextlib.contextmanager
    def mock_send_versioned_push(cls):
        patcher = mock.patch(cls.send_push_func_path)
        mock_obj = patcher.start()
        try:
            yield mock_obj
        finally:
            patcher.stop()

    @classmethod
    def mock_send_versioned_push_decorator(cls, func):
        @wraps(func)
        def patched(self, *args, **kwargs):
            with mock.patch(cls.send_push_func_path) as push_mock:
                result = func(self, push_mock, *args, **kwargs)
                return result
        return patched

    @staticmethod
    def check_push_composer_no_errors(push_composer):
        push_composer.get_kwargs()
        push_composer.get_message()
        push_composer.get_message_type()
