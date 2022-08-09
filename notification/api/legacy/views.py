from rest_framework import generics, mixins, permissions, status, views, viewsets
from rest_framework.response import Response

from rest_condition import Or
from rest_framework_bulk import mixins as bulk_mixins

from base.permissions import IsReadOnly
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from notification.models import APNSDevice, Device, GCMDevice, MerchantMessageTemplate
from radaro_utils.permissions import IsAdminOrManager

from .serializers import (
    APNSDeviceSerializer,
    FCMDeviceSerializer,
    GCMDeviceSerializer,
    MerchantMessageTemplateSerializer,
)


class RegisterDevice(generics.CreateAPIView):
    permission_classes = (permissions.IsAuthenticated, )
    cloud_type = None

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, in_use=True, api_version=self.request.version)

    def create(self, request, *args, **kwargs):
        # Delete all devices on every registering as driver cannot have two or more online devices
        # So `created` is not used - device is always new.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # created = not bool(serializer.instance)
        Device.objects.filter(user=self.request.user).update(in_use=False)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        response_status = status.HTTP_201_CREATED
        return Response(serializer.data, status=response_status, headers=headers)


class RegisterGCMDevice(RegisterDevice):
    serializer_class = GCMDeviceSerializer


class RegisterFCMDevice(RegisterDevice):
    serializer_class = FCMDeviceSerializer


class RegisterAPNSDevice(RegisterDevice):
    serializer_class = APNSDeviceSerializer


class UnregisterDevice(views.APIView):
    permission_classes = (permissions.IsAuthenticated, )

    DEVICE_TYPES = {
        'gcm': GCMDevice,
        'apns': APNSDevice,
        'fcm': GCMDevice
    }

    def post(self, request, device_type, **kwargs):
        if device_type not in self.DEVICE_TYPES:
            return Response(status=404)

        Model = self.DEVICE_TYPES[device_type]

        try:
            device = Model.objects.filter(user=request.user, registration_id=request.data.get('registration_id'))
        except Model.DoesNotExist:
            return Response({'status': 'error', 'message': 'Device does not exist'}, status=400)

        device.update(in_use=False)

        return Response({'status': 'ok', 'message': 'Device successfully removed'}, status=200)


class MerchantMessageTemplatesViewSet(ReadOnlyDBActionsViewSetMixin,
                                      bulk_mixins.BulkUpdateModelMixin,
                                      mixins.RetrieveModelMixin,
                                      mixins.ListModelMixin,
                                      mixins.UpdateModelMixin,
                                      viewsets.GenericViewSet):
    permission_classes = [UserIsAuthenticated, Or(IsAdminOrManager, IsReadOnly)]
    queryset = MerchantMessageTemplate.objects.all()
    serializer_class = MerchantMessageTemplateSerializer

    def get_queryset(self):
        queryset = super(MerchantMessageTemplatesViewSet, self).get_queryset()
        return queryset.filter(merchant_id=self.request.user.current_merchant_id)
