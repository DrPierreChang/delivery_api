from rest_framework import viewsets
from rest_framework.mixins import ListModelMixin

from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from documents.api.mobile.serializers import TagSerializer
from documents.models import Tag


class TagViewSet(ReadOnlyDBActionsViewSetMixin, ListModelMixin, viewsets.GenericViewSet):
    serializer_class = TagSerializer
    permission_classes = [UserIsAuthenticated, IsDriver]
    queryset = Tag.objects.all()

    def get_queryset(self):
        return self.queryset.filter(merchant=self.request.user.current_merchant)
