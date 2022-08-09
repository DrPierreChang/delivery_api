from django.utils.translation import ugettext as _

from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend

from base.utils.views import ReadOnlyDBActionsViewSetMixin
from merchant.permissions import IsNotBlocked
from route_optimisation.api.permissions import RouteOptimisationEnabled
from route_optimisation.models import RouteOptimisation
from webhooks.api.api import MerchantAPIKeyViewSet

from ...permissions import OnlySingleApiKeyAvailable
from ..filters import RouteOptimisationFilter
from .serializers import ExternalRouteOptimisationSerializer


class ExternalRouteOptimisationViewSet(ReadOnlyDBActionsViewSetMixin,
                                       mixins.ListModelMixin,
                                       mixins.RetrieveModelMixin,
                                       mixins.CreateModelMixin,
                                       MerchantAPIKeyViewSet):
    queryset = RouteOptimisation.objects.all().order_by('-id')
    serializer_class = ExternalRouteOptimisationSerializer
    permission_classes = [IsNotBlocked, OnlySingleApiKeyAvailable, RouteOptimisationEnabled]
    filter_backends = (DjangoFilterBackend, )
    filterset_class = RouteOptimisationFilter

    def get_queryset(self):
        return super().get_queryset() \
            .exclude(state=RouteOptimisation.STATE.REMOVED) \
            .prefetch_related_data()

    @action(methods=['post'], detail=True, url_path='notify-customers')
    def notify_customers(self, request, **kwargs):
        instance = self.get_object()
        if instance.state not in (RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING):
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'detail': _('Customers can only be notified in Completed/Running optimisation statuses.')
            })
        elif instance.customers_notified:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={
                'detail': 'Customers have been already notified.'
            })
        instance.notify_customers(request.user)
        return Response()
