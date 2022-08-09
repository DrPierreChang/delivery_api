from rest_framework import viewsets
from rest_framework.mixins import ListModelMixin

from base.permissions import IsGroupManager, IsSubManager
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.models import Label
from merchant.permissions import LabelsEnabled

from .serializers import LabelSerializer


class LabelsViewSet(ReadOnlyDBActionsViewSetMixin, ListModelMixin, viewsets.GenericViewSet):
    queryset = Label.objects.all()
    serializer_class = LabelSerializer
    permission_classes = (UserIsAuthenticated, IsSubManager, LabelsEnabled)

    def get_queryset(self):
        return super().get_queryset().filter(merchant_id=self.request.user.current_merchant_id)


class GroupLabelsViewSet(ReadOnlyDBActionsViewSetMixin, ListModelMixin, viewsets.GenericViewSet):
    queryset = Label.objects.all().select_related('merchant')
    serializer_class = LabelSerializer
    permission_classes = (UserIsAuthenticated, IsGroupManager, LabelsEnabled)

    def get_queryset(self):
        return super().get_queryset()\
            .filter(merchant_id__in=self.request.user.merchants.all().values_list('id', flat=True),
                    merchant__enable_labels=True)
