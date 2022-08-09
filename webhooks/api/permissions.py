from django.utils.translation import ugettext_lazy as _

from rest_framework import permissions

from merchant.models import Merchant
from merchant.permissions import IsNotBlocked, LabelsEnabled, SkillSetsEnabled
from route_optimisation.api.permissions import RouteOptimisationEnabled
from route_optimisation.const import MerchantOptimisationTypes
from webhooks.models import MerchantAPIKey


class ExternalLabelsEnabled(LabelsEnabled):
    def has_permission(self, request, view):
        if request.auth.key_type == MerchantAPIKey.SINGLE:
            return super().has_permission(request, view)
        labels_enabled = request.auth.merchants.values_list('enable_labels', flat=True)
        return any(labels_enabled)


class ExternalSkillSetsEnabled(SkillSetsEnabled):
    def has_permission(self, request, view):
        if request.auth.key_type == MerchantAPIKey.SINGLE:
            return super().has_permission(request, view)
        skill_sets_enabled = request.auth.merchants.values_list('enable_skill_sets', flat=True)
        return any(skill_sets_enabled)


class ExternalIsNotBlocked(IsNotBlocked):
    def has_permission(self, request, view):
        if request.auth.key_type == MerchantAPIKey.SINGLE:
            return super().has_permission(request, view)
        blocked = request.auth.merchants.values_list('is_blocked', flat=True)
        return not any(blocked) or request.method in permissions.SAFE_METHODS


class ExternalRouteOptimisationEnabled(RouteOptimisationEnabled):
    def has_permission(self, request, view):
        if request.auth.key_type == MerchantAPIKey.SINGLE:
            return super().has_permission(request, view)
        ro_types = request.auth.merchants.values_list('route_optimization', flat=True)
        ro_enabled = map(lambda ro_type: ro_type != Merchant.ROUTE_OPTIMIZATION_DISABLED, ro_types)
        return all(ro_enabled)


class OnlySingleApiKeyAvailable(permissions.BasePermission):
    message = 'You can use this API only with "Single API Key"'

    def has_permission(self, request, view):
        return request.auth.key_type == MerchantAPIKey.SINGLE


class ExternalRouteOptimisationAvailable(permissions.BasePermission):
    message = _('External Route optimisation API is not available for you')

    def has_permission(self, request, view):
        return request.user.current_merchant \
               and request.user.current_merchant.route_optimization == MerchantOptimisationTypes.PTV_SMARTOUR_EXPORT
