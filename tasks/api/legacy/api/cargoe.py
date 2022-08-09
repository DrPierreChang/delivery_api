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

from ..serializers.cargoes import DriverOrderSkidSerializer
from ..serializers.orders import DriverOrderSerializer, DriverOrderSerializerV2


class OrderSkidsViewSet(ReadOnlyDBActionsViewSetMixin,
                        mixins.ListModelMixin,
                        mixins.RetrieveModelMixin,
                        viewsets.GenericViewSet):
    permission_classes = [UserIsAuthenticated, IsDriver, SkidsEnabled]
    serializer_class = DriverOrderSkidSerializer
    parent_lookup_field = 'order_order_id'

    @cached_property
    def order(self):
        parent_lookup = self.kwargs.get(self.parent_lookup_field)

        if self.request.version >= 2:
            order = get_object_or_404(Order, driver=self.request.user, pk=parent_lookup)
        else:
            order = get_object_or_404(Order, driver=self.request.user, order_id=parent_lookup)

        return order

    def get_queryset(self):
        order = self.order
        return order.skids.all().exclude(driver_changes=SKID.DELETED)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        order = self.order
        return {**context, 'order': order}

    def get_order_serializer(self, *args, **kwargs):
        if self.request.version >= 2:
            serializer_class = DriverOrderSerializerV2
        else:
            serializer_class = DriverOrderSerializer

        kwargs['context'] = self.get_serializer_context()
        return serializer_class(*args, **kwargs)

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
