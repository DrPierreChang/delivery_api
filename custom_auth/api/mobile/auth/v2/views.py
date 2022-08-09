from collections import namedtuple

from driver.api.mobile.drivers.v2.serializers import V2DriverSerializer

from ..v1.views import UserAuthViewSet

LoginStage = namedtuple('LoginStage', ('PREFETCH', 'LOGIN'))


class V2UserAuthViewSet(UserAuthViewSet):
    driver_serializer_class = V2DriverSerializer
