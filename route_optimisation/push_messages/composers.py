from __future__ import absolute_import, unicode_literals

from django.utils.translation import ugettext_lazy as _

from notification.push_messages.composers import TypedTextPushMessage
from notification.push_messages.mixins import AppealingMessageMixin


class NewRoutePushMessage(AppealingMessageMixin, TypedTextPushMessage):
    message_type = 'NEW_ROUTE'
    message = _('your route was optimised')

    def _get_appeal(self, *args, **kwargs):
        return self.driver_route.driver.first_name

    def _get_postfix(self, *args, **kwargs):
        return ''

    def __init__(self, optimisation, driver_route, *args, **kwargs):
        self.driver_route = driver_route
        self.optimisation = optimisation
        super().__init__(*args, **kwargs)

    def get_kwargs(self, *args, **kwargs):
        kw = super().get_kwargs(*args, **kwargs)
        kw['data']['route_id'] = self.driver_route.id
        kw['data']['day'] = str(self.optimisation.day)
        kw['data']['relevant_for_days'] = kw['data']['day']
        return kw


class SoloOptimisationStatusChangeMessage(TypedTextPushMessage):
    message_type = 'OPTIMIZATION_STATUS_CHANGE'
    message = _('Route optimisation')

    def __init__(self, optimisation, successful):
        self.optimisation = optimisation
        self.successful = successful
        super().__init__()

    def get_message(self, *args, **kwargs):
        status = _('completed') if self.successful else _('failed')
        return '{} {}'.format(self.message, status)

    def get_kwargs(self, *args, **kwargs):
        kw = super().get_kwargs(*args, **kwargs)
        kw['data']['optimization_id'] = self.optimisation.id
        route = self.optimisation.routes.all().first()
        kw['data']['route_id'] = route.id if route else 0
        kw['data']['status'] = 'completed' if self.successful else 'failed'
        return kw


class RemovedOptimisationPushMessage(AppealingMessageMixin, TypedTextPushMessage):
    message_type = "REMOVE_ROUTE"
    message = _('your route was removed')

    def _get_appeal(self, *args, **kwargs):
        return self.driver_route.driver.first_name

    def _get_postfix(self, *args, **kwargs):
        return ''

    def __init__(self, optimisation, driver_route, *args, **kwargs):
        self.driver_route = driver_route
        self.optimisation = optimisation
        super().__init__(*args, **kwargs)

    def get_kwargs(self, *args, **kwargs):
        kw = super().get_kwargs(*args, **kwargs)
        kw['data']["route_id"] = self.driver_route.id
        kw['data']["day"] = str(self.optimisation.day)
        kw['data']["relevant_for_days"] = kw['data']["day"]
        return kw


class RouteChangedMessage(AppealingMessageMixin, TypedTextPushMessage):
    message_type = 'CHANGED_ROUTE'
    message = _('your route was updated')

    def _get_appeal(self, *args, **kwargs):
        return self.driver_route.driver.first_name

    def _get_postfix(self, *args, **kwargs):
        return ''

    def __init__(self, optimisation, driver_route, *args, **kwargs):
        self.driver_route = driver_route
        self.optimisation = optimisation
        super().__init__(*args, **kwargs)

    def get_kwargs(self, *args, **kwargs):
        kw = super().get_kwargs(*args, **kwargs)
        kw['data']['route_id'] = self.driver_route.id
        kw['data']['day'] = str(self.optimisation.day)
        return kw
