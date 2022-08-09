from django.utils.translation import ugettext as _

from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend

from base.utils.views import ReadOnlyDBActionsViewSetMixin
from route_optimisation.models import RouteOptimisation
from webhooks.api.api import MerchantAPIKeyViewSet

from ...permissions import ExternalIsNotBlocked, ExternalRouteOptimisationEnabled
from ..filters import RouteOptimisationFilter
from .serializers.optimisation import ExternalMultiROSerializer, ReadExternalRouteOptimisationSerializer


class ExternalRouteOptimisationViewSetV2(ReadOnlyDBActionsViewSetMixin,
                                         mixins.ListModelMixin,
                                         mixins.RetrieveModelMixin,
                                         mixins.CreateModelMixin,
                                         MerchantAPIKeyViewSet):
    queryset = RouteOptimisation.objects.all().order_by('-id')
    serializer_class = ReadExternalRouteOptimisationSerializer
    create_serializer_class = ExternalMultiROSerializer
    permission_classes = [ExternalIsNotBlocked, ExternalRouteOptimisationEnabled]
    filter_backends = (DjangoFilterBackend, )
    filterset_class = RouteOptimisationFilter

    def get_serializer_class(self):
        if self.action == 'create':
            return self.create_serializer_class
        return super().get_serializer_class()

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.merchant_api_key.is_master_key:
            qs = qs.filter(external_source_id=self.merchant_api_key.pk, external_source_type__model='merchantapikey')
        return qs.exclude(state=RouteOptimisation.STATE.REMOVED).prefetch_related_data()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return_serializer = self.serializer_class(serializer.instance, many=True)
        headers = self.get_success_headers(return_serializer.data)
        return Response(return_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

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
