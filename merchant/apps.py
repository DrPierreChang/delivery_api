from __future__ import unicode_literals

from django.apps import AppConfig


class MerchantConfig(AppConfig):
    name = 'merchant'

    def ready(self):
        import merchant.celery_tasks
        import merchant.signals
