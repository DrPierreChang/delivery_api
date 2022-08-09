from django.urls import include, path

from base.utils import BulkNestedRouter, DefaultRouter

from .barcodes.v1.views import BarcodeViewSet
from .completion_codes.v1.views import TerminateCodeViewSet
from .concatenated_orders.v1.views import ConcatenatedOrderViewSet
from .customers.v1.views import CustomerViewSet, PickupCustomerViewSet
from .daily_driver_orders.v1.views import DailyOrdersViewSet
from .daily_driver_orders.v2.views import V2DailyOrdersViewSet
from .driver_orders.v1.views import OrderSkidsViewSet, OrderViewSet

router = DefaultRouter()
router.register('orders/v1', OrderViewSet)
router.register('completion_codes/v1', TerminateCodeViewSet)
router.register('concatenated_orders/v1', ConcatenatedOrderViewSet)
router.register('barcodes/v1', BarcodeViewSet)
router.register('customers/v1', CustomerViewSet)
router.register('pickup_customers/v1', PickupCustomerViewSet)


order_skids_router = BulkNestedRouter(router, 'orders/v1', lookup='order')
order_skids_router.register('skids', OrderSkidsViewSet, basename='skids')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(order_skids_router.urls)),
    path('daily_orders/v1/', DailyOrdersViewSet.as_view({'get': 'get'})),
    path('daily_orders/v2/', V2DailyOrdersViewSet.as_view({'get': 'get'})),
]
