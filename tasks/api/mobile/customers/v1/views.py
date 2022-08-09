from rest_framework import mixins, viewsets

from django_filters.rest_framework import DjangoFilterBackend

from base.permissions import IsDriver
from custom_auth.permissions import UserIsAuthenticated
from merchant.permissions import IsNotBlocked
from tasks.models import Customer, Pickup
from tasks.permissions import CustomersAutoFillEnabled, PickupsEnabled

from .filters import CustomerFilterSet, PickupCustomerFilterSet
from .serializers import CustomerSerializer, PickupCustomerSerializer


class CustomerViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Customer.objects.all().order_by('-id')

    permission_classes = [UserIsAuthenticated, IsNotBlocked, IsDriver, CustomersAutoFillEnabled]

    serializer_class = CustomerSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = CustomerFilterSet

    def get_queryset(self):
        return super().get_queryset().filter(merchant=self.request.user.current_merchant)


class PickupCustomerViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Pickup.objects.all().order_by('-id')

    permission_classes = [UserIsAuthenticated, IsNotBlocked, IsDriver, PickupsEnabled, CustomersAutoFillEnabled]

    serializer_class = PickupCustomerSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = PickupCustomerFilterSet

    def get_queryset(self):
        return super().get_queryset().filter(merchant=self.request.user.current_merchant)
