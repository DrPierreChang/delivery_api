from __future__ import unicode_literals

from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class RouteOptimisationConfig(AppConfig):
    name = 'route_optimisation'
    verbose_name = _('Route Optimisation')

    def ready(self):
        import route_optimisation.celery_tasks
        import route_optimisation.receivers
