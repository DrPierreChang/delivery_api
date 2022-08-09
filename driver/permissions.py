from rest_framework import permissions


class DriverIsOwnerOrReadOnly(permissions.BasePermission):

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        driver_pk = view.kwargs.get('driver_pk')
        return request.user.is_driver and driver_pk in (str(request.user.pk), 'me')
