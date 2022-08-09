from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED

from base.models import Invite
from custom_auth.api.legacy.api import UserAuthViewSet
from driver.api.mobile.drivers.v1.serializers.driver import DriverSerializer

from .serializers import DriverRegisterSerializer


class InviteViewSet(viewsets.GenericViewSet):
    serializer_class = DriverRegisterSerializer
    driver_serializer_class = DriverSerializer
    permission_classes = [AllowAny]
    queryset = Invite.objects.filter(invited__isnull=True)

    def get_serializer_context(self):
        return {
            **super(InviteViewSet, self).get_serializer_context(),
            'queryset': self.get_queryset(),
        }

    @action(methods=['post', 'get'], detail=False)
    def getcode(self, request, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            fields=('phone', 'app_type', 'app_variant'),
        )
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']
        invite = self.get_queryset().get(phone=phone)
        invite.create_driver_pin(sms_android_verification_hash=serializer.get_sms_android_verification_hash())

        return Response(status=HTTP_200_OK)

    @action(methods=['post'], detail=False)
    def validatecode(self, request, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            fields=('phone', 'pin_code'),
        )
        serializer.is_valid(raise_exception=True)

        return Response(status=HTTP_200_OK)

    @action(methods=['post'], detail=False)
    def password(self, request, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            fields=('phone', 'pin_code', 'password'),
        )
        serializer.is_valid(raise_exception=True)

        password = serializer.validated_data['password']
        phone = serializer.validated_data['phone']
        invite = self.get_queryset().get(phone=phone)
        new_driver = invite.save_driver(password)

        return Response(
            data=self.driver_serializer_class(instance=new_driver, context={'request': self.request}).data,
            status=HTTP_201_CREATED,
            headers={UserAuthViewSet.NEW_TOKEN_HEADER: new_driver.user_auth_tokens.create()},
        )
