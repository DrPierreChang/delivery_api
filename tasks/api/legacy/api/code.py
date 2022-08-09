from django.conf import settings

from rest_framework import serializers, viewsets

from base.permissions import IsManagerOrReadOnly
from custom_auth.permissions import UserIsAuthenticated
from reporting.mixins import TrackableCreateModelMixin, TrackableDestroyModelMixin, TrackableUpdateModelMixin
from tasks.models.terminate_code import SUCCESS_CODES_DISABLED_MSG, TerminateCode

from ..serializers.terminate_code import ErrorCodeSerializer, TerminateCodeSerializer


class TerminateCodeViewSet(TrackableCreateModelMixin,
                           TrackableUpdateModelMixin,
                           TrackableDestroyModelMixin,
                           viewsets.ModelViewSet):
    permission_classes = [UserIsAuthenticated, IsManagerOrReadOnly]
    serializer_class = TerminateCodeSerializer
    queryset = TerminateCode.objects.all()

    def get_queryset(self):
        code_type = self.request.GET.get('type', '').lower()
        if code_type in list(zip(*TerminateCode.TYPE_CHOICES))[0]:
            return self.queryset.filter(type=code_type)
        return self.queryset

    def filter_queryset(self, queryset):
        merchant = self.request.user.current_merchant
        code_type = self.request.GET.get('type', '').lower()
        if code_type == TerminateCode.TYPE_SUCCESS and not merchant.advanced_completion_enabled:
            raise serializers.ValidationError(SUCCESS_CODES_DISABLED_MSG)
        return queryset.filter(merchant=merchant)

    def perform_create(self, serializer):
        serializer.save(merchant=self.request.user.current_merchant)

    def perform_destroy(self, instance):
        deleted_code = instance.code
        code_type = instance.type
        if deleted_code == settings.TERMINATE_CODES[code_type]['OTHER']:
            raise serializers.ValidationError('Can not remove "other" code.')
        if instance.orders.exists():
            raise serializers.ValidationError('This code was used in order.')
        instance.delete()


class ErrorCodeViewSet(TerminateCodeViewSet):
    serializer_class = ErrorCodeSerializer

    def initialize_request(self, request, *args, **kwargs):
        request = super(ErrorCodeViewSet, self).initialize_request(request, *args, **kwargs)
        request.GET._mutable = True
        request.GET.update({'type': TerminateCode.TYPE_ERROR})
        request.GET._mutable = False
        return request
