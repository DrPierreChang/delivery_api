from rest_framework import viewsets
from rest_framework.mixins import ListModelMixin

from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.models import Label
from merchant.permissions import LabelsEnabled

from .serializers import MerchantLabelSerializer


class MerchantLabelsViewSet(ReadOnlyDBActionsViewSetMixin, ListModelMixin, viewsets.GenericViewSet):
    queryset = Label.objects.all()
    serializer_class = MerchantLabelSerializer
    permission_classes = (UserIsAuthenticated, IsDriver, LabelsEnabled)

    def get_queryset(self):
        return super().get_queryset().filter(merchant_id=self.request.user.current_merchant_id)
