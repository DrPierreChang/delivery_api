from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet

from django_filters.rest_framework import DjangoFilterBackend

from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from tasks.models.terminate_code import TerminateCode

from .filters import TerminateCodeFilterSet
from .serializers import TerminateCodeSerializer


class TerminateCodeViewSet(ReadOnlyDBActionsViewSetMixin, mixins.ListModelMixin, GenericViewSet):
    permission_classes = [UserIsAuthenticated, IsDriver]
    serializer_class = TerminateCodeSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = TerminateCodeFilterSet

    queryset = TerminateCode.objects.all()

    def get_queryset(self):
        merchant = self.request.user.current_merchant
        return super().get_queryset().filter(merchant=merchant)
