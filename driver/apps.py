from __future__ import unicode_literals

from django.apps import AppConfig


class DriverConfig(AppConfig):
    name = 'driver'

    def ready(self):
        import driver.celery_tasks
        import driver.signals
