from rest_framework import viewsets
from rest_framework.mixins import ListModelMixin

from django_filters.rest_framework import DjangoFilterBackend
from watson import search as watson
from watson.models import SearchEntry

from base.permissions import IsAdminOrManagerOrObserver
from custom_auth.permissions import UserIsAuthenticated

from .filters import SearchFilterSet
from .serializers import WebSearchSerializer


class WebSearchViewSet(ListModelMixin, viewsets.GenericViewSet):
    queryset = SearchEntry.objects.all().order_by('-pk')
    serializer_class = WebSearchSerializer
    permission_classes = [UserIsAuthenticated, IsAdminOrManagerOrObserver]
    filter_backends = (DjangoFilterBackend,)
    filterset_class = SearchFilterSet

    def get_queryset(self):
        search_results = super().get_queryset().filter(engine_slug=watson.default_search_engine._engine_slug)
        search_results = search_results.prefetch_related('content_type')
        return search_results
