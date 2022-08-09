from rest_framework import permissions


class IsAdminOrManager(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_manager or request.user.is_admin


class IsDeleteMethod(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method == 'DELETE'
