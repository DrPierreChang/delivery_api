import logging
from datetime import timedelta, datetime

from django.contrib.contenttypes.models import ContentType
from django.db import migrations
from django.db.models import Q, Func, DateField
from django.utils import timezone

from radaro_utils.radaro_delayed_tasks.models import DelayedTaskBase
from route_optimisation.const import OldROConstants, OPTIMISATION_TYPES
from route_optimisation.logging import EventType
from route_optimisation.models import RouteOptimisation
from route_optimisation.models.driver_route import DriverRouteColor

logger = logging.getLogger('optimisation')


class MinDateFromArray(Func):
    template = '(select MIN(x) from unnest(%(expressions)s) x)'
    output_field = DateField()


def create_new_from_old(apps, schema):
    RouteOptimization = apps.get_model('routing_optimization', 'routeoptimization')
    migrator = Migrator(apps)
    for ro in get_objects(RouteOptimization):
        try:
            migrator(ro)
        except Exception as exc:
            print('Error', ro.id, exc)


def get_objects(RouteOptimization):
    start_date = (timezone.now() - timedelta(days=2)).date()
    # start_date = (timezone.now() - timedelta(days=60)).date()
    filter_statement = Q(first_optimization_day__gte=start_date) | Q(tool=OldROConstants.PTV_SMARTOUR_EXPORT)
    old = RouteOptimization.objects.annotate(first_optimization_day=MinDateFromArray('days'))\
        .filter(filter_statement)\
        .exclude(is_removed=True)
    print('Overall old RO objects:', RouteOptimization.objects.count())
    print('Count of old RO objects for migration:', old.count())
    return old


def remove_new_from_old(apps, schema):
    pass


class Migrator:
    def __init__(self, apps):
        self.apps = apps

    def __call__(self, old_ro):
        OptimisationTask = self.apps.get_model('route_optimisation', 'optimisationtask')
        DriverRoute = self.apps.get_model('routing_optimization', 'driverroute')
        print('\n', old_ro.id, old_ro.tool, old_ro.days, old_ro.first_optimization_day)
        optimisation = self.create_new_optimisation(old_ro)
        OptimisationTask.objects.create(
            optimisation=optimisation,
            status=DelayedTaskBase.COMPLETED,
            created=old_ro.created,
            modified=old_ro.modified,
        )
        color_generator = DriverRouteColor.gen()
        merchant_timezone = old_ro.merchant.timezone
        for old_route in DriverRoute.objects.filter(optimization_id=old_ro.id):
            self.create_route(old_route, merchant_timezone, optimisation, next(color_generator))

    def create_new_optimisation(self, old_ro):
        NewRouteOptimisation = self.apps.get_model('route_optimisation', 'routeoptimisation')
        state = self._get_state(old_ro)
        optimisation = NewRouteOptimisation.objects.create(
            type=self._get_type(old_ro),
            merchant_id=old_ro.merchant_id,
            created_by_id=old_ro.created_by_id,
            day=old_ro.first_optimization_day,
            google_api_requests=old_ro.google_api_requests,
            state=state,
        )
        logger.info(None, extra=dict(obj=optimisation, event=EventType.OLD_RO, event_kwargs={'old_id': old_ro.id}))
        if state == RouteOptimisation.STATE.FAILED and old_ro.fail_reason:
            logger.info('Fail reason: %s' % old_ro.fail_reason,
                        extra=dict(obj=optimisation, event=EventType.SIMPLE_MESSAGE))
        if old_ro.skipped_orders.count():
            objects = old_ro.skipped_orders.all().values_list('id', flat=True)
            logger.info(None, extra=dict(obj=optimisation, event=EventType.SKIPPED_OBJECTS,
                                         event_kwargs={'objects': objects, 'code': 'order'}))
        return optimisation

    def _get_state(self, old_ro):
        if old_ro.status == DelayedTaskBase.FAILED:
            return RouteOptimisation.STATE.FAILED
        return RouteOptimisation.STATE.COMPLETED

    def _get_type(self, old_ro):
        if old_ro.tool == OldROConstants.PTV_SMARTOUR_EXPORT:
            return OPTIMISATION_TYPES.PTV_EXPORT
        elif old_ro.is_individual:
            return OPTIMISATION_TYPES.SOLO
        else:
            return OPTIMISATION_TYPES.ADVANCED

    def create_route(self, old_route, merchant_timezone, optimisation, color):
        NewDriverRoute = self.apps.get_model('route_optimisation', 'driverroute')
        RoutePoint = self.apps.get_model('routing_optimization', 'routepoint')
        DriverRouteLocation = self.apps.get_model('routing_optimization', 'driverroutelocation')
        Hub = self.apps.get_model('merchant', 'hub')
        if not RoutePoint.objects.filter(route_id=old_route.id).exists():
            return
        start_time = merchant_timezone.localize(datetime.combine(optimisation.day, old_route.start_time))
        end_time = merchant_timezone.localize(datetime.combine(optimisation.day, old_route.end_time))
        route = NewDriverRoute.objects.create(
            optimisation=optimisation,
            driver_id=old_route.driver_id,
            options={},
            start_time=start_time,
            end_time=end_time,
            total_time=None,
            driving_time=old_route.driving_time,
            driving_distance=old_route.driving_distance,
            color=color,
        )
        print('Route', route)
        location_type_id = ContentType.objects.get_for_model(DriverRouteLocation).id
        hub_type_id = ContentType.objects.get_for_model(Hub).id
        points = list(RoutePoint.objects.filter(route_id=old_route.id)
                      .exclude(point_content_type_id=location_type_id))
        for num, old_point in enumerate(points):
            if num == 0 and old_point.point_content_type_id == hub_type_id:
                print('-> Point Start Hub', self.create_point(old_point, route, start_time, start_time))
            elif num == (len(points)-1) and old_point.point_content_type_id == hub_type_id:
                print('-> Point End Hub', self.create_point(old_point, route, end_time, end_time))
            else:
                print('-> Point Order', self.create_point(old_point, route))

    def create_point(self, old_point, route, start_time=None, end_time=None):
        NewRoutePoint = self.apps.get_model('route_optimisation', 'routepoint')
        return NewRoutePoint.objects.create(
            number=old_point.number,
            route=route,
            point_content_type=old_point.point_content_type,
            point_object_id=old_point.point_object_id,
            service_time=None,
            driving_time=None,
            distance=None,
            start_time=start_time,
            end_time=end_time,
            utilized_capacity=None,
            path_polyline=None,
        )


class Migration(migrations.Migration):
    dependencies = [
        ('route_optimisation', '0004_driverroute_state'),
        ('routing_optimization', '0013_routeoptimization_google_api_requests'),
        ('merchant', '0137_merge_20201015_2217'),
    ]

    operations = [
        migrations.RunPython(create_new_from_old, remove_new_from_old),
    ]
