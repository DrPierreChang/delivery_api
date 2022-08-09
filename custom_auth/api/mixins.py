from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .legacy.serializers import PasswordRecoverySerializer, ResetPasswordByEmailSerializer


class ResetPasswordViewMixin(object):
    reset_password_serializer_class = ResetPasswordByEmailSerializer

    @action(methods=['post'], detail=False, permission_classes=[AllowAny], url_path='reset-password')
    def reset_password(self, request, **kwargs):
        serializer = self.get_reset_password_serializer()
        serializer.is_valid(raise_exception=True)
        serializer.send_reset_password_email()
        return Response()

    @action(methods=['post'], detail=False, permission_classes=[AllowAny], url_path='password-recovery')
    def password_recovery(self, request, **kwargs):
        serializer = PasswordRecoverySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response()

    def get_reset_password_serializer(self, **kwargs):
        return self.reset_password_serializer_class(data=self.request.data, **kwargs)


class RetrieveSelfMixin(object):
    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if self.kwargs[lookup_url_kwarg] == 'me':
            obj = self.request.user
            self.check_object_permissions(self.request, obj)
            return obj

        return super(RetrieveSelfMixin, self).get_object()
