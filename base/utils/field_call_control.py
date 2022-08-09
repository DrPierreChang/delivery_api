import threading
import traceback
import warnings
from contextlib import contextmanager

from django.conf import settings


class StaticDataForCallControl(threading.local):
    # Made in such a way that it would work, and accordingly consume resources only during development
    allow_read_merchant = not (settings.DEBUG or 'staging' in settings.CLUSTER_NAME.lower())


class MerchantFieldCallControl:

    def __getattribute__(self, item):
        if static_data.allow_read_merchant:
            return super().__getattribute__(item)

        if item not in ['merchant', 'merchant_id']:
            return super().__getattribute__(item)

        # This part is resource intensive, so it should be called as little as possible
        ignore_functions = {
            'refresh_from_db', 'prefetch_related_objects', '_construct_form', '_changeform_view',
            'items_for_result',
        }
        called_functions = {s.name for s in traceback.extract_stack(limit=10)}
        if ignore_functions & called_functions:
            return super().__getattribute__(item)

        if item == 'merchant':
            msg = f'You must not use the "merchant" field directly! Use "current_merchant".'
            warnings.warn(msg, UserWarning)
            # traceback.print_stack(limit=20)
        if item == 'merchant_id':
            msg = f'You must not use the "merchant_id" field directly! Use "current_merchant_id".'
            warnings.warn(msg, UserWarning)
            # traceback.print_stack(limit=20)

        return super().__getattribute__(item)

    @staticmethod
    @contextmanager
    def allow_field_call():
        old_allow = static_data.allow_read_merchant
        static_data.allow_read_merchant = True
        try:
            yield None
        finally:
            static_data.allow_read_merchant = old_allow


static_data = StaticDataForCallControl()
