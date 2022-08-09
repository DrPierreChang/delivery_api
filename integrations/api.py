from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ModelViewSet

from base.utils.views import ReadOnlyDBActionsViewSetMixin

from .celery_tasks import get_external_orders_from_revel
from .models import RevelSystem
from .serializers import RevelSystemSerializer


class RevelSystemIntegration(ReadOnlyDBActionsViewSetMixin, ModelViewSet):
    queryset = RevelSystem.objects.all().order_by('-pk')
    permission_classes = (AllowAny, )
    serializer_class = RevelSystemSerializer

    def get_queryset(self):
        merchant_id = self.request.user.current_merchant_id

        get_external_orders_from_revel(1)

        return self.queryset.filter(merchant_id=merchant_id)
