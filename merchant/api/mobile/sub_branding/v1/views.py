from rest_framework import viewsets
from rest_framework.mixins import ListModelMixin

from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.models import SubBranding
from merchant.permissions import SubBrandingEnabled

from .serializers import MerchantSubBrandingSerializer


class MerchantSubBrandingViewSet(ReadOnlyDBActionsViewSetMixin, ListModelMixin, viewsets.GenericViewSet):
    queryset = SubBranding.objects.all()
    serializer_class = MerchantSubBrandingSerializer
    permission_classes = (UserIsAuthenticated, IsDriver, SubBrandingEnabled)

    def get_queryset(self):
        return super().get_queryset().filter(merchant_id=self.request.user.current_merchant_id)
