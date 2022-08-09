from collections import namedtuple

from django.db import transaction

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from drf_secure_token.models import Token

from base import signal_senders
from base.models import Member
from base.permissions import IsDriver
from base.signals import logout_event
from custom_auth.api.legacy.serializers import ResetPasswordByEmailSerializer
from driver.api.mobile.drivers.v1.serializers.driver import DriverSerializer
from notification.models import GCMDevice

from .decorators import saml_login
from .serializers import DriverLoginSerializer

LoginStage = namedtuple('LoginStage', ('PREFETCH', 'LOGIN'))


class UserAuthViewSet(viewsets.ViewSet):
    NEW_TOKEN_HEADER = 'X-Token'
    DEFAULT_AUTH, SSO_AUTH = 'default', 'sso'
    stage = LoginStage(**{'PREFETCH': 'prefetch', 'LOGIN': 'login'})

    login_serializer_class = DriverLoginSerializer
    driver_serializer_class = DriverSerializer

    @action(methods=['post'], detail=False, permission_classes=[permissions.AllowAny], url_path='auth-type')
    def authentication_type(self, request, **kwargs):
        serializer = self.login_serializer_class(
            data=request.data, context=self.get_serializer_context(self.stage.PREFETCH), **kwargs
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.prefetch_user()
        auth_type = self.DEFAULT_AUTH if not user or not user.current_merchant.enable_saml_auth else self.SSO_AUTH
        return Response(data={'authentication': auth_type}, status=status.HTTP_200_OK)

    @transaction.atomic
    @saml_login
    @action(methods=['post'], detail=False, permission_classes=[permissions.AllowAny])
    def login(self, request, **kwargs):
        is_force = request.query_params.get('force', False)
        device_id = request.query_params.get('device_id')
        login_serializer = self.login_serializer_class(
            data=self.request.data, context=self.get_serializer_context(self.stage.LOGIN)
        )
        login_serializer.is_valid(raise_exception=True)
        user = login_serializer.authenticate(is_force, device_id)
        return Response(
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(user),
            data=self.driver_serializer_class(user, context={'request': self.request}).data,
        )

    def get_serializer_context(self, stage):
        return {'view': self, 'stage': stage}

    def get_success_headers(self, user):
        return {self.NEW_TOKEN_HEADER: user.user_auth_tokens.create()}

    @action(methods=['delete'], detail=False, permission_classes=[permissions.IsAuthenticated, IsDriver])
    def logout(self, request, **kwargs):
        if request.user.role == Member.DRIVER:
            tokens_for_delete = request.user.user_auth_tokens.all()
        else:
            # if user.role == Member.MANAGER_OR_DRIVER
            # we don't remove all tokens in order to keep existing web sessions
            token = request.auth.key if isinstance(request.auth, Token) else None
            tokens_for_delete = request.user.user_auth_tokens.filter(key=token)
        tokens_for_delete.delete()

        device = request.user.device_set.filter(gcmdevice__registration_id=request.data.get('registration_id'),
                                                gcmdevice__cloud_message_type=GCMDevice.FCM)
        device.update(in_use=False)

        logout_event.send(sender=signal_senders.senders[request.user.role], user=request.user)
        return Response(None, status=status.HTTP_204_NO_CONTENT)

    @action(methods=['post'], detail=False, permission_classes=[permissions.AllowAny], url_path='reset-password')
    def reset_password(self, request, **kwargs):
        serializer = ResetPasswordByEmailSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        serializer.send_reset_password_email()
        return Response()
