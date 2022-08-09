from __future__ import unicode_literals

from django.apps import AppConfig


class RadaroRouterConfig(AppConfig):
    name = 'radaro_router'

    def ready(self):
        import celery_tasks
