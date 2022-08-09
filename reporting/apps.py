from __future__ import unicode_literals

from django.apps import AppConfig


class ReportingConfig(AppConfig):
    name = 'reporting'

    def ready(self):
        import reporting.celery_tasks
        import reporting.receivers
