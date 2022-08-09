from rest_framework import viewsets
from rest_framework.mixins import ListModelMixin

from base.models import Member
from base.permissions import IsGroupManager, IsSubManager
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated

from .serializers import DriverSerializer


class DriverViewSet(ReadOnlyDBActionsViewSetMixin, ListModelMixin, viewsets.GenericViewSet):
    queryset = Member.drivers.all()
    serializer_class = DriverSerializer
    permission_classes = (UserIsAuthenticated, IsSubManager)

    def get_queryset(self):
        return super().get_queryset().filter(merchant_id=self.request.user.current_merchant_id).order_by('-pk')


class GroupDriverViewSet(ReadOnlyDBActionsViewSetMixin, ListModelMixin, viewsets.GenericViewSet):
    queryset = Member.drivers.all()
    serializer_class = DriverSerializer
    permission_classes = (UserIsAuthenticated, IsGroupManager)

    def get_queryset(self):
        return super().get_queryset()\
            .filter(merchant_id__in=self.request.user.merchants.all().values_list('id', flat=True))
