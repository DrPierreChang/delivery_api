from django.urls import include, path

from base.utils import BulkNestedRouter, DefaultRouter, NestedSimpleRouter
from tasks.api.legacy.api import (
    CustomerOrderViewSet,
    CustomerSurveysViewSet,
    CustomerViewSet,
    OrderBarcodesViewSet,
    OrderViewSet,
    PickupOrderViewSet,
    PickupViewSet,
    PublicMerchantViewSet,
    PublicOrderReportViewSet,
    TerminateCodeViewSet,
)
from tasks.api.legacy.views import CsvBulkView

from .group_orders.views import GroupOrdersViewSet
from .group_orders_dev.views import WebGroupOrdersViewSet
from .orders.views import AvailableConcatenatedOrderViewSet, WebOrderViewSet
from .public_order.views import WebPublicMerchantViewSet, WebPublicOrderViewSet
from .subbrand_orders.views import SubbrandOrderViewSet
from .subbrand_orders_dev.views import WebSubbrandOrderViewSet

router = DefaultRouter()
router.register(r'orders', OrderViewSet)
router.register(r'customers', CustomerViewSet)
router.register(r'pickups', PickupViewSet)
router.register(r'public-merchant', PublicMerchantViewSet)
router.register(r'bulk', CsvBulkView)
router.register(r'terminate-codes', TerminateCodeViewSet)

customers_router = NestedSimpleRouter(router, r'customers', lookup=CustomerViewSet.url_router_lookup)
customers_router.register(r'orders', CustomerOrderViewSet)

pickups_router = NestedSimpleRouter(router, r'pickups', lookup=PickupViewSet.url_router_lookup)
pickups_router.register(r'orders', PickupOrderViewSet)

public_merchant_router = NestedSimpleRouter(router, r'public-merchant', lookup=PublicMerchantViewSet.url_router_lookup)
public_merchant_router.register(r'public-report', PublicOrderReportViewSet)

customer_survey_router = NestedSimpleRouter(customers_router, r'orders', lookup='customer_order')
customer_survey_router.register(r'surveys', CustomerSurveysViewSet)

barcodes_router = BulkNestedRouter(router, r'orders', lookup='order')
barcodes_router.register(r'barcodes', OrderBarcodesViewSet, basename='barcodes')

subbrand_router = DefaultRouter()
subbrand_router.register('orders', SubbrandOrderViewSet)

group_router = DefaultRouter()
group_router.register('orders', GroupOrdersViewSet)

web_router = DefaultRouter()

web_router.register(r'orders', WebOrderViewSet)
web_router.register(r'subbrand/orders', WebSubbrandOrderViewSet)
web_router.register(r'group/orders', WebGroupOrdersViewSet)
web_router.register(r'public_report/merchant', WebPublicMerchantViewSet)

web_orders_router = NestedSimpleRouter(web_router, 'orders', lookup='orders')
web_orders_router.register('available_orders', AvailableConcatenatedOrderViewSet, basename='available_orders')

web_public_merchant_router = NestedSimpleRouter(web_router, 'public_report/merchant', lookup='merchant')
web_public_merchant_router.register('orders', WebPublicOrderViewSet)

urlpatterns = [
    path('', include(router.urls), {'api_version': 2}),
    path('', include(customers_router.urls), {'api_version': 2}),
    path('', include(pickups_router.urls), {'api_version': 2}),
    path('', include(public_merchant_router.urls), {'api_version': 2}),
    path('', include(customer_survey_router.urls), {'api_version': 2}),
    path('', include(barcodes_router.urls), {'api_version': 2}),
    path('subbrand/', include(subbrand_router.urls)),
    path('group/', include(group_router.urls)),
    path('dev/', include(web_router.urls)),
    path('dev/', include(web_public_merchant_router.urls)),
    path('dev/', include(web_orders_router.urls)),
]
