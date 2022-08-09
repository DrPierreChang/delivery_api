import logging
import random

from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField
from django.db import models

from model_utils import Choices

from merchant.models import Hub
from route_optimisation.const import RoutePointKind
from route_optimisation.logging import EventType
from tasks.models import Order

logger = logging.getLogger('optimisation')


class DriverRouteColor:
    colors = (
        '#BF4040', '#BF4A40', '#BF5540', '#BF6040', '#BF6A40', '#BF7540', '#BF8040', '#BF8A40', '#BF9540', '#BF9F40',
        '#BFAA40', '#BFB540', '#BFBF40', '#B5BF40', '#AABF40', '#9FBF40', '#95BF40', '#8ABF40', '#7FBF40', '#75BF40',
        '#6ABF40', '#60BF40', '#55BF40', '#4ABF40', '#40BF40', '#3FBE4A', '#40BF55', '#40BF60', '#40BF6A', '#40BF75',
        '#40BF7F', '#40BF8A', '#40BF95', '#40BF9F', '#40BFAA', '#40BFB5', '#40BFBF', '#40B5BF', '#40AABF', '#409FBF',
        '#4095BF', '#408ABF', '#4080BF', '#4075BF', '#406ABF', '#4060BF', '#4055BF', '#404ABF', '#4040BF', '#4A40BF',
        '#5540BF', '#6040BF', '#6A40BF', '#7540BF', '#8040BF', '#8A40BF', '#9540BF', '#9F40BF', '#AA40BF', '#B540BF',
        '#BF40BF', '#BF40B5', '#BF40AA', '#BF409F', '#BF4095', '#BF408A', '#BF407F', '#BF4075', '#BF406A', '#BF4060',
        '#BF4055', '#BF404A',
    )

    @classmethod
    def gen(cls):
        colors = list(cls.colors)
        random.shuffle(colors)
        for color in colors:
            yield color


class DriverRouteColorPicker:
    def __init__(self):
        self.initial_colors = list(DriverRouteColor.colors)

    def __call__(self, exclude_colors):
        colors = list(set(self.initial_colors).difference(set(exclude_colors)))
        if colors:
            color = random.choice(colors)
            self.initial_colors.remove(color)
        else:
            color = random.choice(list(DriverRouteColor.colors))
        return color


class DriverRouteQuerySet(models.QuerySet):
    def prefetch_generic_relations(self):
        from . import DriverRoute, RoutePoint
        content_types = ContentType.objects.get_for_models(Order, Hub)
        hubs_qs = RoutePoint.objects.all().prefetch_for_content_type(content_types[Hub])
        orders_qs = RoutePoint.objects.all().prefetch_for_content_type(content_types[Order])
        prefetch_hubs = models.Prefetch(
            'points', to_attr=DriverRoute.get_prefetch_attr_name(Hub), queryset=hubs_qs
        )
        prefetch_orders = models.Prefetch(
            'points', to_attr=DriverRoute.get_prefetch_attr_name(Order), queryset=orders_qs
        )
        return self.prefetch_related(prefetch_hubs, prefetch_orders)

    def prefetch_generic_relations_for_web_api(self):
        from . import DriverRoute, DriverRouteLocation, RoutePoint
        content_types = ContentType.objects.get_for_models(Order, Hub, DriverRouteLocation)
        base_qs = RoutePoint.objects.all().order_by('number')
        hubs_qs = base_qs.filter(point_content_type=content_types[Hub]).prefetch_related('point_object__location')
        orders_qs = base_qs.filter(point_content_type=content_types[Order])\
            .prefetch_related('point_object__concatenated_order', 'point_object__merchant')
        locations_qs = base_qs.filter(point_content_type=content_types[DriverRouteLocation])
        breaks_qs = base_qs.filter(point_kind=RoutePointKind.BREAK)
        prefetch_hubs = models.Prefetch(
            'points', to_attr=DriverRoute.get_prefetch_attr_name(Hub), queryset=hubs_qs
        )
        prefetch_orders = models.Prefetch(
            'points', to_attr=DriverRoute.get_prefetch_attr_name(Order), queryset=orders_qs
        )
        prefetch_locations = models.Prefetch(
            'points', to_attr=DriverRoute.get_prefetch_attr_name(DriverRouteLocation), queryset=locations_qs
        )
        prefetch_breaks = models.Prefetch(
            'points', to_attr=DriverRoute.get_prefetch_attr_name(for_break=True), queryset=breaks_qs
        )
        return self.prefetch_related(prefetch_hubs, prefetch_orders, prefetch_locations, prefetch_breaks)


class DriverRouteManager(models.Manager):
    _queryset_class = DriverRouteQuerySet

    def get_used_colors_for_date(self, driver, date):
        qs = self.get_queryset().filter(
            driver=driver,
            optimisation__day=date,
            state__in=(DriverRoute.STATE.CREATED, DriverRoute.STATE.RUNNING))
        return qs.values_list('color', flat=True)


class DriverRoute(models.Model):
    optimisation = models.ForeignKey('route_optimisation.RouteOptimisation', related_name='routes',
                                     on_delete=models.CASCADE)
    driver = models.ForeignKey('base.Member', related_name='routes', on_delete=models.PROTECT)
    color = models.CharField(max_length=10)

    options = JSONField(blank=True, null=True)

    total_time = models.PositiveIntegerField(blank=True, null=True)
    driving_time = models.PositiveIntegerField(blank=True, null=True)
    driving_distance = models.PositiveIntegerField(blank=True, null=True)

    real_time = models.PositiveIntegerField(blank=True, null=True)
    real_distance = models.PositiveIntegerField(blank=True, null=True)

    start_time = models.DateTimeField(blank=True, null=True)
    end_time = models.DateTimeField(blank=True, null=True)

    STATE = Choices(
        ('CREATED', 'Created'),
        ('RUNNING', 'Running'),
        ('FINISHED', 'Finished'),
        ('FAILED', 'Failed'),
    )
    state = models.CharField(max_length=12, choices=STATE, default=STATE.CREATED)

    objects = DriverRouteManager()

    class Meta:
        unique_together = ('optimisation', 'color')

    @staticmethod
    def get_prefetch_attr_name(model=None, for_break=False):
        if for_break:
            return 'route_points_breaks'
        assert model is not None
        from route_optimisation.models import DriverRouteLocation
        prefetch_attr_name_map = {
            DriverRouteLocation: 'route_points_locations',
            Order: 'route_points_orders',
            Hub: 'route_points_hubs',
        }
        return prefetch_attr_name_map[model]

    def get_typed_route_points(self, point_kind):
        model, filter_kwargs = None, {}
        attr_name = None
        if point_kind == RoutePointKind.HUB:
            model = Hub
        elif point_kind == RoutePointKind.LOCATION:
            from route_optimisation.models import DriverRouteLocation
            model = DriverRouteLocation
        elif point_kind == RoutePointKind.PICKUP:
            model = Order
            filter_kwargs = {'point_kind': RoutePointKind.PICKUP}
        elif point_kind == RoutePointKind.DELIVERY:
            model = Order
            filter_kwargs = {'point_kind': RoutePointKind.DELIVERY}
        elif point_kind == RoutePointKind.BREAK:
            model = None
            attr_name = self.get_prefetch_attr_name(for_break=True)
            filter_kwargs = {'point_kind': RoutePointKind.BREAK}
        if attr_name is None:
            attr_name = self.get_prefetch_attr_name(model)
        return self._get_route_points(model, attr_name, filter_kwargs)

    def _get_route_points(self, model, attr_name, filter_kwargs):
        if attr_name and hasattr(self, attr_name):
            result = getattr(self, attr_name)
            for k, v in filter_kwargs.items():
                result = filter(lambda item: getattr(item, k) == v, result)
        else:
            result = self.points.all()
            if model is not None:
                result = result.prefetch_for_content_type(ContentType.objects.get_for_model(model))
            result = result.filter(**filter_kwargs)
        return list(result)

    def state_to(self, state):
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.ROUTE_STATE_CHANGE,
                                     event_kwargs={'state': state, 'route': self}))
        self.state = state
        self.save(update_fields=('state',))
