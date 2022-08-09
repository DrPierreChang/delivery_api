from rest_framework import permissions


class SoDChecklistEnabled(permissions.BasePermission):
    message = 'Your merchant doesn\'t have ability to create Start-of-Day checklists'

    def has_permission(self, request, view):
        if request.user.current_merchant.sod_checklist is not None:
            return True


class EoDChecklistEnabled(permissions.BasePermission):
    message = 'Your merchant doesn\'t have ability to create End-of-Day checklists'

    def has_permission(self, request, view):
        if request.user.current_merchant.eod_checklist is not None:
            return True
