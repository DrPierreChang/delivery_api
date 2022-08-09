from rest_framework import mixins, viewsets

from merchant.models import Merchant
from tasks.models import Order

from ...legacy.api.mixins import ObjectByUIDB64ApiBase
from .serializers import WebPublicOrderSerializer


class WebPublicMerchantViewSet(viewsets.GenericViewSet):
    queryset = Merchant.objects.all()
    lookup_field = 'uidb64'
    url_router_lookup = 'merchant'


class WebPublicOrderViewSet(mixins.RetrieveModelMixin, ObjectByUIDB64ApiBase):
    queryset = Order.objects.all()
    serializer_class = WebPublicOrderSerializer
    lookup_field = 'order_token'
    uidb64_lookup_viewset = WebPublicMerchantViewSet

    def filter_queryset(self, queryset):
        return super().filter_queryset(queryset).filter(merchant_id=self._object_id)

    def get_queryset(self):
        return super().get_queryset().select_related(
            'merchant', 'sub_branding', 'customer', 'pickup', 'driver', 'manager',
            'deliver_address', 'pickup_address', 'ending_point', 'starting_point',
        ).prefetch_related('labels', 'skill_sets', 'barcodes', 'skids')
