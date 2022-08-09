from rest_framework import mixins, viewsets

from base.utils.views import ReadOnlyDBActionsViewSetMixin
from merchant.models import Merchant
from tasks.models import Order

from ..serializers import PublicReportSerializer
from .mixins import ObjectByUIDB64ApiBase


class PublicMerchantViewSet(viewsets.GenericViewSet):
    queryset = Merchant.objects.all()
    lookup_field = 'uidb64'
    url_router_lookup = 'merchant'


class PublicOrderReportViewSet(ReadOnlyDBActionsViewSetMixin,
                               mixins.RetrieveModelMixin,
                               ObjectByUIDB64ApiBase):
    queryset = Order.objects.all()
    serializer_class = PublicReportSerializer
    lookup_field = 'order_token'
    uidb64_lookup_viewset = PublicMerchantViewSet

    def filter_queryset(self, queryset):
        return super(PublicOrderReportViewSet, self).filter_queryset(queryset).filter(merchant_id=self._object_id)

    def get_queryset(self):
        return super(PublicOrderReportViewSet, self).get_queryset().select_related(
            'merchant', 'sub_branding', 'customer', 'driver',
            'deliver_address', 'ending_point', 'starting_point',
        )\
            .prefetch_related('labels', 'skill_sets', 'barcodes')
