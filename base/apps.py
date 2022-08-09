from __future__ import unicode_literals

from django.apps import AppConfig

from watson import search as watson


class BaseConfig(AppConfig):
    name = 'base'

    def ready(self):
        import base.celery_tasks
        Member = self.get_model('Member')
        watson.register(Member, fields=('username', 'first_name', 'last_name', 'email', 'phone'))
