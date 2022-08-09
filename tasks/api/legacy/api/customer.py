from rest_framework import viewsets

from tasks.models import Customer, Pickup


class CustomerViewSet(viewsets.GenericViewSet):
    queryset = Customer.objects.all()
    lookup_field = 'uidb64'
    url_router_lookup = 'customer'


class PickupViewSet(viewsets.GenericViewSet):
    queryset = Pickup.objects.all()
    lookup_field = 'uidb64'
    url_router_lookup = 'pickup'
