from django.utils.functional import cached_property

from rest_framework import mixins, status, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.permissions import SkidsEnabled
from reporting.context_managers import track_fields_on_change
from tasks.models import SKID, Order

from ..serializers import DriverOrderSerializer, DriverOrderSkidSerializer


class OrderSkidsViewSet(ReadOnlyDBActionsViewSetMixin,
                        mixins.ListModelMixin,
                        mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    permission_classes = [UserIsAuthenticated, IsDriver, SkidsEnabled]
    serializer_class = DriverOrderSkidSerializer
    parent_lookup_field = 'order_pk'

    @cached_property
    def order(self):
        parent_lookup = self.kwargs.get(self.parent_lookup_field)
        order = get_object_or_404(Order, driver=self.request.user, pk=parent_lookup)
        return order

    def get_queryset(self):
        return self.order.skids.all().exclude(driver_changes=SKID.DELETED)

    def get_serializer_context(self):
        return {'order': self.order, **super().get_serializer_context()}

    def get_order_serializer(self, *args, **kwargs):
        return DriverOrderSerializer(*args, **kwargs, context=self.get_serializer_context())

    def create(self, request, *args, **kwargs):
        with track_fields_on_change(self.order, initiator=request.user):
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            if getattr(self.order, '_prefetched_objects_cache', None):
                self.order._prefetched_objects_cache = {}

        return Response(self.get_order_serializer(self.order).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        with track_fields_on_change(self.order, initiator=request.user):
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            if getattr(self.order, '_prefetched_objects_cache', None):
                self.order._prefetched_objects_cache = {}

        return Response(self.get_order_serializer(self.order).data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        with track_fields_on_change(self.order, initiator=request.user):
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.destroy()
            if getattr(self.order, '_prefetched_objects_cache', None):
                self.order._prefetched_objects_cache = {}

        return Response(self.get_order_serializer(self.order).data, status=status.HTTP_200_OK)
