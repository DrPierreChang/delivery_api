from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from tasks.models import Order

from ..serializers.orders import RetrieveOrderSerializer


class MerchantAdminOrderApiBase(viewsets.GenericViewSet):
    lookup_field = 'order_token'
    queryset = Order.objects.all()
    permission_classes = [AllowAny]

    def get_object(self):
        queryset = self.get_queryset()
        order_token = self.kwargs.get(self.lookup_field)
        obj = get_object_or_404(queryset, order_token=order_token)
        obj_merchant = getattr(obj, 'merchant', None)
        hash_str = self.request.query_params.get('hash', None)
        if obj_merchant and obj.merchant_daily_hash() == hash_str:
            return obj
        else:
            raise PermissionDenied('Invalid credentials or order has no merchant.')


class MerchantAdminOrderViewSet(MerchantAdminOrderApiBase):
    @action(methods=['get'], detail=True)
    def path_replay(self, request, **kwargs):
        instance = self.get_object()
        order_data = RetrieveOrderSerializer(instance, context={'request': request}).data
        all_routes = instance.driver.get_all_routes(instance.get_track())
        return Response(data={'route': all_routes, 'order': order_data})
