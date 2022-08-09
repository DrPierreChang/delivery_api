from ..v1.views import DriverViewSet
from .serializers import V2DriverSerializer


class V2DriverViewSet(DriverViewSet):
    serializer_class = V2DriverSerializer
