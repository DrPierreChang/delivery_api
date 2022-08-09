from rest_framework import generics, status
from rest_framework.response import Response

from base.permissions import IsDriver
from custom_auth.permissions import UserIsAuthenticated
from notification.api.mobile.devices.v1.serializers import FCMDeviceSerializer
from notification.models import Device


class RegisterDeviceView(generics.CreateAPIView):
    permission_classes = [UserIsAuthenticated, IsDriver]
    serializer_class = FCMDeviceSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': self.request})
        serializer.is_valid(raise_exception=True)
        Device.objects.filter(user=self.request.user).update(in_use=False)
        self.perform_create(serializer)
        return Response(status=status.HTTP_201_CREATED)
