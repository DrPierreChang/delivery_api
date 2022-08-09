from rest_framework import permissions

from driver.utils import WorkStatus


class IsOwnedByMerchant(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return(
            obj.merchant == request.user.current_merchant
        )


class IsReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_admin


class IsObserver(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_observer


class IsDriverOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS or request.user.is_driver


class IsWorking(permissions.BasePermission):
    message = 'Action is unavailable - you\'re offline.'

    def has_permission(self, request, view):
        return request.user.work_status == WorkStatus.WORKING


class IsManagerOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_manager or request.user.is_admin or request.method in permissions.SAFE_METHODS


class IsManager(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_manager or request.user.is_admin


class IsDriver(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_driver


class IsSubManager(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_submanager


class IsAdminOrManagerOrObserver(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_manager or request.user.is_admin or request.user.is_observer


class IsGroupManager(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_group_manager
