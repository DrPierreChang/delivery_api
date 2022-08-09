from datetime import time, timedelta
from operator import attrgetter, itemgetter

from django.test import override_settings
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import mock

from notification.tests.mixins import NotificationTestMixin
from route_optimisation.const import OPTIMISATION_TYPES, RoutePointKind
from route_optimisation.models import DriverRoute, RoutePoint
from schedule.models import Schedule
from tasks.mixins.order_status import OrderStatus

from ...push_messages.composers import RouteChangedMessage
from ..test_utils.distance_matrix import TestDiMaCache
from ..test_utils.setting import DriverBreakSetting
from .api_settings import APISettings
from .mixins import ORToolsMixin
from .optimisation_expectation import OptimisationExpectation
from .tests_concatenated_orders import enable_concatenated_orders_for_merchant
from .tests_pickup_feature import enable_pickup_for_merchant


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class ReorderSequenceTestCase(NotificationTestMixin, ORToolsMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.manager)

    def test_reorder_in_case_two_routes(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, start_time=(5,), end_time=(23, 30), capacity=15)
        settings.order(1, '-37.6780953, 145.1290807', driver=1)
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(3, '-35.5418094, 144.9643013', driver=1)
        settings.order(4, '-35.5418094, 144.9643013', driver=1)
        settings.order(5, '-37.9202176, 145.2230781', driver=1)
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id_1 = self.run_optimisation(settings, expectation)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id_1, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')

        new_settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        new_settings.copy_hubs(settings)
        new_settings.copy_drivers(settings)
        new_settings.order(6, '-37.926451, 144.998992', driver=1)
        new_settings.order(7, '-37.6780953, 145.1290807', driver=1)
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id_2 = self.run_optimisation(new_settings, expectation)
        route_two = DriverRoute.objects.get(optimisation_id=optimisation_id_2, driver_id=new_settings.drivers_map[1].id)
        points_two = RoutePoint.objects.filter(route=route_two).order_by('number')

        sequence = list(map(attrgetter('id'), points_two))
        sequence[1], sequence[2] = sequence[2], sequence[1]
        self.reorder_sequence(optimisation_id_2, route_two.id, sequence)

        points = points_one.filter(point_kind__in=[RoutePointKind.DELIVERY, RoutePointKind.PICKUP])
        sequence = [
            points_one.get(number=1).id,
            points.get(point_object_id=settings.orders_map[3].id).id,
            points.get(point_object_id=settings.orders_map[1].id).id,
            points.get(point_object_id=settings.orders_map[2].id).id,
            points.get(point_object_id=settings.orders_map[5].id).id,
            points.get(point_object_id=settings.orders_map[4].id).id,
            points_one.get(number=7).id,
        ]
        resp = self.reorder_sequence(optimisation_id_1, route_one.id, sequence,
                                     expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Updated route intersects with other route of driver', resp.data['detail'])

    def test_reorder_simple(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, start_time=(8,), end_time=(11, 30), capacity=15)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=15)
        settings.order(1, '-37.6780953, 145.1290807', driver=1, deliver_after_time=(8, 50), deliver_before_time=(9, 10))
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(3, '-35.5418094, 144.9643013', driver=2)
        settings.order(4, '-37.9202176, 145.2230781', driver=2)
        settings.order(5, '-37.9202176, 145.2230781', driver=1, deliver_after_time=(9, 30), deliver_before_time=(9, 50))
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        self.assertEqual(0, len(list(filter(None, map(attrgetter('start_time_known_to_customer'), points_one)))))

        resp = self.client.post('{}{}/notify_customers'.format(self.api_url, optimisation_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        self.assertEqual(
            points_one.filter(point_kind=RoutePointKind.DELIVERY).count(),
            len(list(filter(None, map(attrgetter('start_time_known_to_customer'), points_one))))
        )
        initial_sequence = list(map(attrgetter('id'), points_one))

        # can't move hubs
        sequence = list(initial_sequence)
        sequence[0], sequence[2] = sequence[2], sequence[0]
        resp = self.reorder_sequence(optimisation_id, route_one.id, sequence,
                                     expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Route must start at hub or specific location but not order', resp.data['detail'])

        # Cant move jobs because of time validations
        sequence = list(initial_sequence)
        sequence[1], sequence[2] = sequence[2], sequence[1]
        resp = self.reorder_sequence(optimisation_id, route_one.id, sequence,
                                     expected_status=status.HTTP_400_BAD_REQUEST)
        expected_errors = (
            'Point {} is out of delivery window'.format(points_one[2].point_object.title),
            'Point {} is out of delivery window'.format(points_one[1].point_object.title),
            'Route time is out of schedule of driver',
        )
        for error_text in expected_errors:
            for error in resp.data['errors']['can_force']:
                if error_text in error:
                    break
            else:
                raise self.failureException('{} is not in errors'.format(error_text))

        # Fix orders and schedule times
        points_one[2].point_object.deliver_after = None
        points_one[2].point_object.save(update_fields=('deliver_after',))
        points_one[1].point_object.deliver_before += timedelta(hours=4)
        points_one[1].point_object.save(update_fields=('deliver_before',))
        schedule, _ = Schedule.objects.get_or_create(member=settings.drivers_map[1])
        schedule.schedule['constant'][self._day.weekday()]['end'] = time(hour=11, minute=50)
        schedule.save(update_fields=('schedule',))

        # Successfully move jobs
        resp = self.reorder_sequence(optimisation_id, route_one.id, sequence)
        self.assert_updated_sequence(resp.json(), route_one.id, sequence)
        expected_in_log = 'Sequence of route {} for  changed by '.format(route_one.id)
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        points_jobs = RoutePoint.objects.filter(route__optimisation_id=optimisation_id).order_by('number') \
            .filter(point_kind=RoutePointKind.DELIVERY)
        self.assertEqual(len(list(filter(lambda p: p.start_time_known_to_customer != p.start_time, points_jobs))), 3)
        resp = self.client.post('{}{}/notify_customers'.format(self.api_url, optimisation_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        points_jobs = RoutePoint.objects.filter(route__optimisation_id=optimisation_id).order_by('number') \
            .filter(point_kind=RoutePointKind.DELIVERY)
        self.assertEqual(len(list(filter(lambda p: p.start_time_known_to_customer != p.start_time, points_jobs))), 0)

        # Same route sequence
        resp = self.reorder_sequence(optimisation_id, route_one.id, sequence,
                                     expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Route sequence is not changed', resp.data['detail'])

        # can move when first jobs deadline changed and bad. Change following orders sequence
        p = RoutePoint.objects.filter(route_id=route_one.id, point_kind=RoutePointKind.DELIVERY)\
            .order_by('number').first()
        p.point_object.deliver_after = p.start_time + timedelta(minutes=20)
        p.point_object.save(update_fields=('deliver_after',))
        sequence = list(map(attrgetter('id'), RoutePoint.objects.filter(route_id=route_one.id).order_by('number')))
        sequence[3], sequence[2] = sequence[2], sequence[3]
        self.reorder_sequence(optimisation_id, route_one.id, sequence)

        # can't move finished
        order_for_process = RoutePoint.objects.get(id=sequence[1]).point_object
        self.change_order_status(settings.drivers_map[1], order=order_for_process,
                                 order_status=OrderStatus.IN_PROGRESS)
        self.change_order_status(settings.drivers_map[1], order=order_for_process,
                                 order_status=OrderStatus.DELIVERED)
        sequence[1], sequence[2] = sequence[2], sequence[1]
        resp = self.reorder_sequence(optimisation_id, route_one.id, sequence,
                                     expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Can not reorder finished order', resp.data['detail'])

    def test_reorder_with_break(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, start_time=(8,), end_time=(15, 30), capacity=15,
                        breaks=[DriverBreakSetting((9, 30), (10, 0), 15)])
        settings.order(1, '-37.6780953, 145.1290807', driver=1)
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(4, '-37.9202176, 145.2230781', driver=1)
        settings.order(5, '-37.9202176, 145.2230781', driver=1)
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)

        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.DELIVERY, '08:42:56', '08:52:56'),
            (RoutePointKind.BREAK, '09:30:00', '10:00:00'),
            (RoutePointKind.DELIVERY, '10:03:41', '10:13:41'),
            (RoutePointKind.DELIVERY, '10:13:41', '10:23:41'),
            (RoutePointKind.DELIVERY, '11:01:43', '11:11:43'),
            (RoutePointKind.HUB, '11:52:39', '11:52:39'),
        )
        get = self.client.get(self.api_url + str(optimisation_id))
        for point, point_kind_time in zip(get.json()['routes'][0]['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')

        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        sequence = list(
            map(attrgetter('id'), filter(lambda x: x.point_kind != RoutePointKind.BREAK, points_one))
        )
        sequence[1], sequence[2] = sequence[2], sequence[1]

        resp = self.reorder_sequence(optimisation_id, route_one.id, sequence)
        self.assert_updated_sequence(resp.json(), route_one.id, sequence)
        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.DELIVERY, '08:47:50', '08:57:50'),
            (RoutePointKind.BREAK, '09:30:00', '10:00:00'),
            (RoutePointKind.DELIVERY, '10:10:41', '10:20:41'),
            (RoutePointKind.DELIVERY, '11:01:26', '11:11:26'),
            (RoutePointKind.DELIVERY, '11:49:28', '11:59:28'),
            (RoutePointKind.HUB, '12:40:24', '12:40:24'),
        )
        for point, point_kind_time in zip(resp.json()['routes'][0]['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        current = 0
        for point in points_one:
            current += 1
            self.assertEqual(current, point.number)
        expected_in_log = 'Sequence of route {} for  changed by '.format(route_one.id)
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_force_flag(self, push_mock):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, start_time=(8,), end_time=(11, 30), capacity=15)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=15)
        settings.order(1, '-37.6780953, 145.1290807', driver=1, deliver_after_time=(8, 50), deliver_before_time=(9, 10))
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(3, '-35.5418094, 144.9643013', driver=2)
        settings.order(4, '-37.9202176, 145.2230781', driver=2)
        settings.order(5, '-37.9202176, 145.2230781', driver=1, deliver_after_time=(9, 30), deliver_before_time=(9, 50))
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        sequence = list(map(attrgetter('id'), points_one))
        sequence[1], sequence[2] = sequence[2], sequence[1]
        resp = self.reorder_sequence(optimisation_id, route_one.id, sequence,
                                     expected_status=status.HTTP_400_BAD_REQUEST)
        expected_errors = (
            'Point {} is out of delivery window'.format(points_one[2].point_object.title),
            'Point {} is out of delivery window'.format(points_one[1].point_object.title),
            'Route time is out of schedule of driver',
        )
        for error_text in expected_errors:
            for error in resp.data['errors']['can_force']:
                if error_text in error:
                    break
            else:
                raise self.failureException('{} is not in errors'.format(error_text))

        date = timezone.now()
        push_mock.reset_mock()
        resp = self.reorder_sequence(optimisation_id, route_one.id, sequence, force=True)
        self.assert_updated_sequence(resp.json(), route_one.id, sequence)
        self.assertEqual(push_mock.call_count, 1)
        push_composer = push_mock.call_args_list[0][0][0]
        self.assertTrue(isinstance(push_composer, RouteChangedMessage))
        self.check_push_composer_no_errors(push_composer)
        events_resp = self.client.get('/api/v2/new-events/?date_since={}'.format(date.isoformat().replace('+', 'Z')))
        self.assertEqual(len(events_resp.json()['events']), 1)
        self.assertEqual(events_resp.json()['events'][0]['type'], 'routeoptimisation')
        self.assertEqual(events_resp.json()['events'][0]['object_id'], optimisation_id)
        self.assertEqual(events_resp.json()['events'][0]['event'], 'model_changed')

    def assert_updated_sequence(self, resp, route_id, sequence):
        for route in resp['routes']:
            if route['id'] != route_id:
                continue
            points = filter(lambda x: x['point_kind'] != RoutePointKind.BREAK, route['points'])
            points = list(map(itemgetter('id'), sorted(points, key=itemgetter('number'))))
            self.assertEqual(points, sequence)

    def reorder_sequence(self, optimisation_id, route_id, new_sequence,
                         expected_status=status.HTTP_200_OK, force=False):
        distance_matrix_cache = TestDiMaCache(polylines=True)
        path = 'route_optimisation.utils.managing.reorder_sequence.SequenceReorderService.get_distance_matrix_cache'
        with mock.patch(path, return_value=distance_matrix_cache):
            resp = self.client.post('{}{}/reorder_sequence'.format(self.api_url, optimisation_id), {
                'route': route_id,
                'sequence': new_sequence,
                'force': force,
            })
        self.assertEqual(resp.status_code, expected_status)
        return resp

    def change_order_status(self, driver, order, order_status):
        self.client.force_authenticate(driver)
        resp = self.client.put('{url}{id}/status/'.format(url=self.orders_url, id=order.id), {'status': order_status})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.manager)

    @enable_pickup_for_merchant
    def test_reorder_with_pickup(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=15)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=15)
        settings.order(1, '-37.6780953, 145.1290807', driver=1, pickup_address='-35.5418094, 144.9643013')
        settings.order(2, '-37.926451, 144.998992', driver=1, pickup_address='-37.9202176, 145.2230781')
        settings.order(3, '-35.5418094, 144.9643013', driver=2)
        settings.order(4, '-37.9202176, 145.2230781', driver=2)
        settings.order(5, '-37.9202176, 145.2230781', driver=1, pickup_address='-37.926451, 144.998992')
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        sequence = list(map(attrgetter('id'), points_one))
        pickup_idx, pickup_point = None, None
        for idx, point in enumerate(points_one):
            if point.point_kind == RoutePointKind.PICKUP:
                pickup_idx = idx
                pickup_point = point
                break
        sequence[pickup_idx], sequence[6] = sequence[6], sequence[pickup_idx]
        resp = self.reorder_sequence(optimisation_id, route_one.id, sequence,
                                     expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Pickup can not be after delivery', resp.data['detail'])

        sequence = list(map(attrgetter('id'), points_one))
        delivery_idx, delivery_point = None, None
        for idx, point in enumerate(points_one):
            if point.point_kind == RoutePointKind.DELIVERY and point.point_object_id == pickup_point.point_object_id:
                delivery_idx = idx
                break
        order_for_process = pickup_point.point_object
        self.change_order_status(settings.drivers_map[1], order=order_for_process,
                                 order_status=OrderStatus.PICK_UP)
        self.change_order_status(settings.drivers_map[1], order=order_for_process,
                                 order_status=OrderStatus.PICKED_UP)
        sequence[delivery_idx], sequence[delivery_idx+1] = sequence[delivery_idx+1], sequence[delivery_idx]
        self.reorder_sequence(optimisation_id, route_one.id, sequence)

    @enable_pickup_for_merchant
    @enable_concatenated_orders_for_merchant
    def test_reorder_concatenated(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=5)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=15)
        settings.order(1, '-37.8421644,144.9399743', driver=1, pickup_address='-37.755938,145.706767', capacity=4,
                       deliver_after_time=(7,),)
        settings.order(2, '-37.8421644,144.9399743', driver=1, pickup_address='-37.5795883,143.8387151',
                       deliver_after_time=(7,),)
        settings.order(3, '-37.8421644,144.9399743', driver=1, deliver_after_time=(7,),)
        settings.concatenated_order(4, (1, 2, 3))
        settings.order(5, '-37.8485871,144.6670881', driver=2, pickup_address='-37.698763,145.054753', capacity=2)
        settings.order(6, '-37.698763,145.054753', driver=1)
        settings.set_use_vehicle_capacity(True)
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        route_two = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[2].id)
        points_two = RoutePoint.objects.filter(route=route_two).order_by('number')
        self.assertEqual(points_one.count(), 6)
        self.assertEqual(points_two.count(), 4)
        initial_sequence = list(map(attrgetter('id'), points_one))
        sequence = list(initial_sequence)
        sequence[3], sequence[4] = sequence[4], sequence[3]
        resp = self.reorder_sequence(optimisation_id, route_one.id, sequence,
                                     expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Pickup can not be after delivery', resp.data['detail'])
        sequence = list(initial_sequence)
        sequence[3], sequence[2] = sequence[2], sequence[3]
        resp = self.reorder_sequence(optimisation_id, route_one.id, sequence,
                                     expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Capacity of target driver car can not satisfy route capacity', resp.data['detail'])
        settings.drivers_map[1].car.capacity += 1
        settings.drivers_map[1].car.save(update_fields=('capacity',))
        resp = self.reorder_sequence(optimisation_id, route_one.id, sequence)
        self.assert_updated_sequence(resp.json(), route_one.id, sequence)
