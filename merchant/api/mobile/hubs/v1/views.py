from rest_framework import viewsets
from rest_framework.mixins import ListModelMixin

from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.models import Hub
from merchant.permissions import HubsEnabled

from .filters import DriverHubsFilterBackend
from .serializers import HubSerializer


class MerchantHubViewSet(ReadOnlyDBActionsViewSetMixin, ListModelMixin, viewsets.GenericViewSet):
    queryset = Hub.objects.all().order_by('-pk')
    serializer_class = HubSerializer
    permission_classes = (UserIsAuthenticated, IsDriver, HubsEnabled)
    filter_backends = (DriverHubsFilterBackend,)

    def filter_queryset(self, queryset):
        return super().filter_queryset(queryset).filter(merchant_id=self.request.user.current_merchant_id)
