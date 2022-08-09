
from django.conf.urls import include, url

from base.utils import BulkNestedRouter, DefaultRouter, NestedSimpleRouter

from .api import (
    CustomerOrderViewSet,
    CustomerSurveysViewSet,
    CustomerViewSet,
    ErrorCodeViewSet,
    MerchantAdminOrderViewSet,
    OrderBarcodesViewSet,
    OrderViewSet,
    PickupOrderViewSet,
    PickupViewSet,
    PublicMerchantViewSet,
    PublicOrderReportViewSet,
    TerminateCodeViewSet,
)
from .api.cargoe import OrderSkidsViewSet
from .views import CsvBulkView

router = DefaultRouter()
router.register(r'orders', OrderViewSet)
router.register(r'customers', CustomerViewSet)
router.register(r'pickups', PickupViewSet)
router.register(r'public-merchant', PublicMerchantViewSet)
router.register(r'bulk', CsvBulkView)
router.register(r'order-stats', MerchantAdminOrderViewSet)
router.register(r'terminate-codes', TerminateCodeViewSet)
# For backward compatibility
router.register(r'error-codes', ErrorCodeViewSet)

customers_router = NestedSimpleRouter(router, r'customers', lookup=CustomerViewSet.url_router_lookup)
customers_router.register(r'orders', CustomerOrderViewSet)

pickups_router = NestedSimpleRouter(router, r'pickups', lookup=PickupViewSet.url_router_lookup)
pickups_router.register(r'orders', PickupOrderViewSet)

public_merchant_router = NestedSimpleRouter(router, r'public-merchant', lookup=PublicMerchantViewSet.url_router_lookup)
public_merchant_router.register(r'public-report', PublicOrderReportViewSet)

customer_survey_router = NestedSimpleRouter(customers_router, r'orders', lookup='customer_order')
customer_survey_router.register(r'surveys', CustomerSurveysViewSet)

order_barcodes_router = BulkNestedRouter(router, r'orders', lookup='order')
order_barcodes_router.register(r'barcodes', OrderBarcodesViewSet, basename='barcodes')

order_skids_router = BulkNestedRouter(router, r'orders', lookup='order')
order_skids_router.register(r'skids', OrderSkidsViewSet, basename='skids')

tasks_api_patterns = \
    [
        url(r'', include(router.urls)),
        url(r'', include(customers_router.urls)),
        url(r'', include(pickups_router.urls)),
        url(r'', include(public_merchant_router.urls)),
        url(r'', include(customer_survey_router.urls)),
        url(r'', include(order_barcodes_router.urls)),
        url(r'', include(order_skids_router.urls)),
    ]
