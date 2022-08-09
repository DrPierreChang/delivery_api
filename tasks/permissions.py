from rest_framework import permissions
from rest_framework.exceptions import APIException

from .models import BulkDelayedUpload


class CanCreateOrder(permissions.BasePermission):

    def has_permission(self, request, view):
        if not (request.user.is_authenticated and request.user.current_merchant):
            return False

        if request.user.is_manager or request.user.is_admin:
            return True
        return request.user.is_driver and request.user.current_merchant.driver_can_create_job


class CanProcessBulkUpload(permissions.BasePermission):
    message = None

    def has_object_permission(self, request, view, obj):
        try:
            if obj.is_in(BulkDelayedUpload.IN_PROGRESS):
                raise APIException('Last operation was not finished. Try later.')
            elif obj.is_in(BulkDelayedUpload.FAILED):
                raise APIException('Task failed: all operations are forbidden.')
            elif obj.is_in(BulkDelayedUpload.CONFIRMED):
                raise APIException('Task confirmed: no need for any operation.')
            elif obj.is_in(BulkDelayedUpload.CREATED):
                raise APIException('Task is not ready for any operation.')
        except APIException as ex:
            self.message = ex.detail
            return False
        return True


class CanDriverCreateOrder(permissions.BasePermission):
    def has_permission(self, request, view):
        if not (request.user.is_authenticated and request.user.current_merchant):
            return False
        if request.method != 'POST':
            return True
        return request.user.is_driver and request.user.current_merchant.driver_can_create_job


class CustomersAutoFillEnabled(permissions.BasePermission):
    message = "You don't have ability to search for customers."

    def has_permission(self, request, view):
        return request.user.current_merchant.enable_auto_complete_customer_fields


class PickupsEnabled(permissions.BasePermission):
    message = "You don't have ability to use a pickup."

    def has_permission(self, request, view):
        return request.user.current_merchant.use_pick_up_status
