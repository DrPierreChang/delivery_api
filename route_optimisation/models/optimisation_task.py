from django.core.cache import caches
from django.db import models

from kombu import uuid

from delivery.celery import app
from radaro_utils.radaro_delayed_tasks.models import DelayedTaskBase


class OptimisationTask(DelayedTaskBase):
    optimisation = models.OneToOneField('route_optimisation.RouteOptimisation', on_delete=models.CASCADE,
                                        related_name='delayed_task')

    def _when_begin(self, *args, **kwargs):
        pass

    def _when_fail(self, *args, **kwargs):
        pass

    def _when_complete(self, *args, **kwargs):
        pass

    @property
    def cache(self):
        return caches['optimisation']

    @property
    def delayed_task_cache_key(self):
        return f'optimisation-task-pool-{self.optimisation.id}'

    def register_delayed_task(self, celery_task_id=None):
        celery_task_id = celery_task_id or uuid()
        tasks = self.cache.get(self.delayed_task_cache_key, [])
        tasks.append(celery_task_id)
        self.cache.set(self.delayed_task_cache_key, tasks, timeout=12*60*60)
        return celery_task_id

    def terminate_tasks_pool(self):
        tasks = self.cache.get(self.delayed_task_cache_key, [])
        app.control.revoke(tasks, terminate=True, signal='SIGUSR1')
