from driver.api.mobile.drivers.v2.serializers import V2DriverSerializer

from ..v1.views import InviteViewSet


class V2InviteViewSet(InviteViewSet):
    driver_serializer_class = V2DriverSerializer
