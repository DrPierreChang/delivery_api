from django.utils.translation import ugettext_lazy as _

from rest_framework import permissions

from merchant.models import Merchant


class RouteOptimisationEnabled(permissions.BasePermission):
    message = _('Route optimisation is not active for you')

    def has_permission(self, request, view):
        return request.user.current_merchant \
               and request.user.current_merchant.route_optimization != Merchant.ROUTE_OPTIMIZATION_DISABLED
