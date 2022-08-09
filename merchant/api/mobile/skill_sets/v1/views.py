from rest_framework import viewsets
from rest_framework.mixins import ListModelMixin

from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.models import SkillSet
from merchant.permissions import SkillSetsEnabled

from .filters import SkillSetAssignedFilterBackend
from .serializers import SkillSetSerializer


class MerchantSkillSetViewSet(ReadOnlyDBActionsViewSetMixin, ListModelMixin, viewsets.GenericViewSet):
    queryset = SkillSet.objects.all()
    serializer_class = SkillSetSerializer
    permission_classes = (UserIsAuthenticated, IsDriver, SkillSetsEnabled)
    filter_backends = (SkillSetAssignedFilterBackend,)

    def filter_queryset(self, queryset):
        return super().filter_queryset(queryset).filter(merchant_id=self.request.user.current_merchant_id)
