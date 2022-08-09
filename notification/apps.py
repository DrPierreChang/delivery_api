from __future__ import unicode_literals

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = 'notification'

    def ready(self):
        import notification.celery_tasks
