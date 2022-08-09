from ..v1.views import DriverChecklistViewSet
from .serializers import V2ResultAnswerSerializer, V2ResultChecklistSerializer


class V2DriverChecklistViewSet(DriverChecklistViewSet):
    serializer_class = V2ResultChecklistSerializer
    answer_serializer_class = V2ResultAnswerSerializer
