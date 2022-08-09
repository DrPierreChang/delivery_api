from __future__ import unicode_literals

from django.apps import AppConfig


class MerchantExtensionConfig(AppConfig):
    name = 'merchant_extension'
    verbose_name = 'Merchant Extension'

    def ready(self):
        import merchant_extension.celery_tasks
