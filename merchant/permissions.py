from django.utils.translation import ugettext_lazy as _

from rest_framework import permissions


class IsNotBlocked(permissions.BasePermission):
    message = 'You don\'t have ability to perform this action because' \
              ' your account has been suspended for non-payment.'

    def has_permission(self, request, view):
        if not request.user.current_merchant.is_blocked or \
                (request.user.current_merchant.is_blocked and request.method in permissions.SAFE_METHODS):
            return True


class LabelsEnabled(permissions.BasePermission):
    message = _("You don't have ability to perform this action because labels aren't enabled. " 
                "Please, contact administrator.")

    def has_permission(self, request, view):
        if request.user.is_group_manager:
            return any(request.user.merchants.all().values_list('enable_labels', flat=True))
        return request.user.current_merchant.enable_labels


class SkillSetsEnabled(permissions.BasePermission):
    message = _("You don't have ability to perform this action because skill sets aren't enabled. " 
                "Please, contact administrator.")

    def has_permission(self, request, view):
        return request.user.current_merchant.enable_skill_sets


class BarcodesEnabled(permissions.BasePermission):
    message = _("You don't have ability to perform this action because barcodes aren't enabled. " 
                "Please, contact administrator.")

    def has_permission(self, request, view):
        return request.user.current_merchant.option_barcodes != request.user.current_merchant.TYPES_BARCODES.disable


class ConfirmationDocumentEnabled(permissions.BasePermission):
    message = "You don't have ability to perform this action because confirmation documents aren't enabled. " \
              "Please, contact administrator."

    def has_permission(self, request, view):
        return request.user.current_merchant.enable_delivery_confirmation_documents


class SkidsEnabled(permissions.BasePermission):
    message = _("You don't have ability to perform this action because SKIDs aren't enabled. " 
                "Please, contact administrator.")

    def has_permission(self, request, view):
        return request.user.current_merchant.enable_skids


class SubBrandingEnabled(permissions.BasePermission):
    message = _("You don't have ability to perform this action because subbranding aren't enabled. " 
                "Please, contact administrator.")

    def has_permission(self, request, view):
        return request.user.current_merchant.use_subbranding


class HubsEnabled(permissions.BasePermission):
    message = _("You don't have ability to perform this action because hubs aren't enabled. " 
                "Please, contact administrator.")

    def has_permission(self, request, view):
        return request.user.current_merchant.use_hubs


class ConcatenatedOrdersEnabled(permissions.BasePermission):
    message = "You don't have ability to perform this action because concatenated orders aren't enabled. " \
              "Please, contact administrator."

    def has_permission(self, request, view):
        return request.user.current_merchant.enable_concatenated_orders
