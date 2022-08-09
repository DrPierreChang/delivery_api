from __future__ import unicode_literals

from django.apps import AppConfig

from watson import search as watson


class TasksConfig(AppConfig):
    name = 'tasks'

    def ready(self):
        import tasks.celery_tasks
        import tasks.signal_receivers
        Order = self.get_model('Order')
        OrderLocation = self.get_model('OrderLocation')
        watson.register(Order, fields=(
            'customer__phone', 'customer__name', 'customer__email', 'order_id',
            'deliver_address__address', 'title', 'description', 'comment'))
        watson.register(OrderLocation, exclude=('location', 'description'))
