from django.contrib.contenttypes.models import ContentType
from django.db.models import Prefetch, Q, prefetch_related_objects

from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from base.permissions import IsDriver
from custom_auth.permissions import UserIsAuthenticated
from merchant.models import Hub
from merchant.permissions import IsNotBlocked
from merchant_extension.models import ResultChecklistConfirmationPhoto
from route_optimisation.models import DriverRoute, DriverRouteLocation, RouteOptimisation, RoutePoint
from tasks.models import SKID, ConcatenatedOrder, Order

from .filters import ConcatenatedOrderDateFilterSet, OptimisationDateFilterSet, OrderDateFilterSet
from .serializers import DailyOrdersSerializer
from .utils import keydefaultdict


class DailyOrdersViewSet(viewsets.ViewSet):
    permission_classes = [UserIsAuthenticated, IsNotBlocked, IsDriver]
    serializer_class = DailyOrdersSerializer

    def get_route_optimisations_qs(self):
        user = self.request.user
        allowed_statuses = [
            RouteOptimisation.STATE.COMPLETED,
            RouteOptimisation.STATE.RUNNING,
            RouteOptimisation.STATE.FINISHED,
        ]
        qs = DriverRoute.objects.filter(driver=user, optimisation__state__in=allowed_statuses)

        content_types = ContentType.objects.get_for_models(Order, Hub, DriverRouteLocation)

        hubs_qs = RoutePoint.objects.all().filter(point_content_type=content_types[Hub])
        hubs_qs = hubs_qs.prefetch_related('point_object__location')

        orders_qs = RoutePoint.objects.all().filter(point_content_type=content_types[Order])
        concatenated_orders_qs = RoutePoint.objects.none()
        if user.current_merchant.enable_concatenated_orders:
            concatenated_orders_qs = orders_qs.filter(point_object_id__in=Order.aggregated_objects.filter(
                Q(concatenated_order__isnull=False) | Q(is_concatenated_order=True)
            ))
            orders_qs = orders_qs.filter(point_object_id__in=Order.aggregated_objects.filter(
                concatenated_order__isnull=True, is_concatenated_order=False
            ))
        orders_qs = orders_qs.prefetch_related('point_object')
        concatenated_orders_qs = concatenated_orders_qs.prefetch_related('point_object__concatenated_order')

        locations_qs = RoutePoint.objects.all().filter(point_content_type=content_types[DriverRouteLocation])
        locations_qs = locations_qs.prefetch_related('point_object')

        qs = qs.prefetch_related(
            Prefetch('points', to_attr='hubs', queryset=hubs_qs),
            Prefetch('points', to_attr='orders', queryset=orders_qs),
            Prefetch('points', to_attr='concatenated_orders', queryset=concatenated_orders_qs),
            Prefetch('points', to_attr='locations', queryset=locations_qs),
        )
        return qs

    @staticmethod
    def prefetch_for_route_orders(routes):
        orders, concatenated_orders = [], []
        for route in routes:
            for order in route.orders:
                orders.append(order.point_object)
            for order in route.concatenated_orders:
                orders.append(order.point_object)
                if order.point_object.is_concatenated_order:
                    order.point_object._self_concatenated = ConcatenatedOrder.objects.get(id=order.point_object_id)
                    concatenated_orders.append(order.point_object._self_concatenated)
                    orders.append(order.point_object._self_concatenated)
                else:
                    concatenated_orders.append(order.point_object.concatenated_order)
                    orders.append(order.point_object.concatenated_order)

        prefetch_list = (
            'customer', 'pickup', 'deliver_address', 'pickup_address', 'driver_checklist',
            'labels', 'barcodes', 'skill_sets', 'terminate_codes',
            'pick_up_confirmation_photos', 'pre_confirmation_photos', 'order_confirmation_photos',
            'order_confirmation_documents',
            Prefetch('status_events', to_attr=Order.status_events.cache_name),
            Prefetch('order_route_point', to_attr=Order.order_route_point.cache_name),
            Prefetch('skids', to_attr='not_deleted_skids', queryset=SKID.objects.exclude(driver_changes=SKID.DELETED)),
            Prefetch(
                'driver_checklist__confirmation_photos',
                queryset=ResultChecklistConfirmationPhoto.objects.only('id')
            ),
        )
        prefetch_related_objects(orders, *prefetch_list)

        only_for_concatenated_prefetch_list = (
            Prefetch('orders', queryset=Order.objects.all().prefetch_for_mobile_api().order_inside_concatenated()),
        )
        prefetch_related_objects(concatenated_orders, *only_for_concatenated_prefetch_list)

        return routes

    def get_route_optimisations(self):
        qs = self.get_route_optimisations_qs()

        filterset = OptimisationDateFilterSet(data=self.request.query_params, queryset=qs, request=self.request)
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)

        qs = filterset.filter_queryset(qs)
        routes = list(qs)
        self.prefetch_for_route_orders(routes)
        return routes

    def get_orders_queryset(self):
        qs = Order.objects.all().prefetch_for_mobile_api().filter(driver=self.request.user)

        filterset = OrderDateFilterSet(data=self.request.query_params, queryset=qs, request=self.request)
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)

        return filterset.filter_queryset(qs)

    def get_concatenated_orders_queryset(self):
        qs = ConcatenatedOrder.objects.all().prefetch_for_mobile_api().filter(driver=self.request.user)

        filterset = ConcatenatedOrderDateFilterSet(data=self.request.query_params, queryset=qs, request=self.request)
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)

        return filterset.filter_queryset(qs)

    def get_serializer_context(self):
        return {
            'request': self.request,
            'format': self.format_kwarg,
            'view': self
        }

    def get(self, request, *args, **kwargs):
        routes = list(self.get_route_optimisations())

        ro_order_ids = []
        order_ct = ContentType.objects.get_for_model(Order)
        for route in routes:
            for point in route.points.all():
                if point.point_content_type_id == order_ct.id:
                    ro_order_ids.append(point.point_object_id)

        orders = self.get_orders_queryset().exclude(id__in=ro_order_ids)
        concatenated_orders = ConcatenatedOrder.objects.none()

        if request.user.current_merchant.enable_concatenated_orders:
            orders = orders.filter(concatenated_order__isnull=True)
            concatenated_orders = self.get_concatenated_orders_queryset().exclude(id__in=ro_order_ids)

        daily_jobs = keydefaultdict(lambda day: {
            'delivery_date': day,
            'route_optimisations': [],
            'orders': [],
            'concatenated_orders': [],
        })

        for order in orders:
            daily_jobs[order.delivery_date]['orders'].append(order)
        for concatenated_order in concatenated_orders:
            daily_jobs[concatenated_order.deliver_day]['concatenated_orders'].append(concatenated_order)
        for route in routes:
            daily_jobs[route.optimisation.day]['route_optimisations'].append(route)

        daily_jobs_list = list(daily_jobs.values())
        daily_jobs_list.sort(key=lambda x: x['delivery_date'])

        serializer = self.serializer_class(
            instance=daily_jobs_list,
            many=True,
            context=self.get_serializer_context()
        )
        return Response(data=serializer.data)
