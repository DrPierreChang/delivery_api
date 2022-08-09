from datetime import time, timedelta
from operator import attrgetter

from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import mock

from notification.tests.mixins import NotificationTestMixin
from route_optimisation.const import OPTIMISATION_TYPES, RoutePointKind
from route_optimisation.models import DriverRoute, RouteOptimisation, RoutePoint
from schedule.models import Schedule
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.push_notification.push_messages.order_change_status_composers import (
    AssignedMessage,
    BulkAssignedMessage,
    BulkUnassignedMessage,
    UnassignedMessage,
)

from ...push_messages.composers import NewRoutePushMessage, RouteChangedMessage
from ..test_utils.distance_matrix import TestDiMaCache
from ..test_utils.setting import DriverBreakSetting
from .api_settings import APISettings, SoloAPISettings
from .mixins import ORToolsMixin
from .optimisation_expectation import OptimisationExpectation
from .tests_concatenated_orders import enable_concatenated_orders_for_merchant
from .tests_pickup_feature import enable_pickup_for_merchant


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class MoveJobsTestCase(NotificationTestMixin, ORToolsMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.manager)

    @enable_pickup_for_merchant
    def test_move_with_pickup(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=15)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=15)
        settings.order(1, '-37.6780953, 145.1290807', driver=1, pickup_address='-37.9202176, 145.2230781')
        settings.order(2, '-37.926451, 144.998992', driver=1, pickup_address='-37.9202176, 145.2230781')
        settings.order(3, '-35.5418094, 144.9643013', driver=2)
        settings.order(4, '-37.9202176, 145.2230781', driver=2)
        settings.order(5, '-37.9202176, 145.2230781', driver=1, pickup_address='-37.926451, 144.998992')
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        route_two = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[2].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')

        points_ids = list(map(attrgetter('id'), points_one))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:1], settings.drivers_map[2],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('object does not exist', resp.data['detail'])
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[1:2], settings.drivers_map[2],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('object does not exist', resp.data['detail'])

        points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[2])
        self.assertEqual(RoutePoint.objects.filter(route=route_one).count(), 4)
        self.assertEqual(RoutePoint.objects.filter(route=route_two).count(), 8)

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_move_with_force(self, push_mock):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, start_time=(8,), end_time=(19,), capacity=15)
        settings.order(6, '-37.6780953, 145.1290807', driver=1, deliver_after_time=(13,), deliver_before_time=(16,))
        settings.order(7, '-37.926451, 144.998992', driver=1, deliver_after_time=(13,), deliver_before_time=(16,))
        settings.order(8, '-37.9202176, 145.2230781', driver=1, deliver_after_time=(13,), deliver_before_time=(16,))
        settings.set_working_hours((13,), (20,))
        expectation = OptimisationExpectation(skipped_orders=0)
        self.run_optimisation(settings, expectation)

        settings.driver(member_id=2, start_hub=1, end_hub=1, start_time=(8,), end_time=(16, 50), capacity=15)
        settings.order(1, '-37.6780953, 145.1290807', driver=1, deliver_after_time=(8, 40), deliver_before_time=(9, 20))
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(3, '-35.5418094, 144.9643013', driver=2,
                       deliver_after_time=(12, 40), deliver_before_time=(13, 10))
        settings.order(4, '-37.9202176, 145.2230781', driver=2, deliver_after_time=(8, 50), deliver_before_time=(9, 20))
        settings.order(5, '-37.9202176, 145.2230781', driver=1, deliver_after_time=(9, 40), deliver_before_time=(10, 8))
        settings.set_working_hours((8,), (20,))
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)

        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        route_two = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[2].id)
        points_two = RoutePoint.objects.filter(route=route_two).order_by('number')
        initial_points_ids_1 = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        initial_points_ids_2 = list(map(attrgetter('id'), points_two.filter(point_kind=RoutePointKind.DELIVERY)))

        points_ids = list(initial_points_ids_2)
        resp = self.move_orders(optimisation_id, route_two.id, points_ids[1:], settings.drivers_map[1],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Can not place new orders in target drivers route', resp.data['detail'])
        resp = self.move_orders(optimisation_id, route_two.id, points_ids[1:], settings.drivers_map[1],
                                expected_status=status.HTTP_400_BAD_REQUEST, force=True)
        self.assertIn('Can not place new orders in target drivers route', resp.data['detail'])
        points_ids = list(initial_points_ids_1)
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[2],
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
        push_mock.reset_mock()
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[2],
                                force=True)
        self.assert_moved_orders(resp.json(), route_one.id, 1, points_ids[:2], settings.drivers_map[2], 4)
        expected_in_log = 'Moved 2 jobs from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        self.assertEqual(push_mock.call_count, 4)
        bulk_assigned_push_sent, bulk_unassigned_push_sent = False, False
        changed_route_msg_1, changed_route_msg_2 = False, False
        for (push_composer,), _ in push_mock.call_args_list:
            if isinstance(push_composer, BulkAssignedMessage):
                self.assertEqual(push_composer.driver.id, settings.drivers_map[2].id)
                bulk_assigned_push_sent = True
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, BulkUnassignedMessage):
                self.assertEqual(push_composer.driver.id, settings.drivers_map[1].id)
                bulk_unassigned_push_sent = True
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, RouteChangedMessage):
                if push_composer.driver_route.id == route_one.id:
                    changed_route_msg_1 = True
                if push_composer.driver_route.id == route_two.id:
                    changed_route_msg_2 = True
                self.check_push_composer_no_errors(push_composer)
        self.assertTrue(bulk_assigned_push_sent)
        self.assertTrue(bulk_unassigned_push_sent)
        self.assertTrue(changed_route_msg_1)
        self.assertTrue(changed_route_msg_2)

    @enable_pickup_for_merchant
    @enable_concatenated_orders_for_merchant
    def test_move_concatenated(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=5)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=4)
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
        points_one = RoutePoint.objects.filter(route=route_one).order_by('point_object_id')
        initial_points = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        points_ids = list(initial_points)
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:1], settings.drivers_map[2],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Can not place new orders in target drivers route', resp.data['detail'])
        settings.drivers_map[2].car.capacity += 1
        settings.drivers_map[2].car.save(update_fields=('capacity',))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:1], settings.drivers_map[2])
        self.assert_moved_orders(resp.json(), route_one.id, 1, points_ids[:1], settings.drivers_map[2], 2)

    def test_move_with_capacity_and_skillset(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.skill(1)
        settings.skill(2)
        settings.driver(member_id=1, start_hub=1, end_hub=1, skill_set=(1, 2), capacity=15)
        settings.driver(member_id=2, start_hub=1, end_hub=1, skill_set=(1,), capacity=3)
        settings.order(1, '-37.6780953, 145.1290807', driver=1, skill_set=(2,), capacity=1)
        settings.order(2, '-37.926451, 144.998992', driver=1, skill_set=(1,), capacity=2)
        settings.order(3, '-35.5418094, 144.9643013', driver=1, skill_set=(1,), capacity=1)
        settings.order(4, '-37.9202176, 145.2230781', driver=2, skill_set=(1,), capacity=2)
        settings.set_use_vehicle_capacity(True)
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)

        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')\
            .filter(point_kind=RoutePointKind.DELIVERY).values_list('id', flat=True)

        points_ids = list(points_one.filter(point_object_id=settings.orders_map[1].id))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids, settings.drivers_map[2],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Target driver can not satisfy order skill set', resp.data['detail'])
        points_ids = list(points_one.filter(point_object_id=settings.orders_map[2].id))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids, settings.drivers_map[2],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Can not place new orders in target drivers route', resp.data['detail'])

        points_ids = list(points_one.filter(point_object_id=settings.orders_map[3].id))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids, settings.drivers_map[2])
        self.assert_moved_orders(resp.json(), route_one.id, 2, points_ids, settings.drivers_map[2], 2)

    def test_move_to_started_existing_route_with_capacity(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=15)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=3)
        settings.order(1, '-37.6780953, 145.1290807', driver=1, capacity=1)
        settings.order(2, '-37.926451, 144.998992', driver=2, capacity=1)
        settings.order(3, '-35.5418094, 144.9643013', driver=2, capacity=1)
        settings.order(4, '-37.9202176, 145.2230781', driver=2, capacity=1)
        settings.order(5, '-37.6780953, 145.1290807', driver=1, capacity=1)
        settings.set_use_vehicle_capacity(True)
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)

        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        route_two = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[2].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')\
            .filter(point_kind=RoutePointKind.DELIVERY).values_list('id', flat=True)

        points_ids = list(points_one.filter(point_object_id=settings.orders_map[5].id))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids, settings.drivers_map[2],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Can not place new orders in target drivers route', resp.data['detail'])

        points_two = list(RoutePoint.objects.filter(route=route_two).order_by('number')
                          .filter(point_kind=RoutePointKind.DELIVERY))
        order_for_process = points_two[0].point_object
        self.change_order_status(settings.drivers_map[2], order=order_for_process, order_status=OrderStatus.IN_PROGRESS)
        self.change_order_status(settings.drivers_map[2], order=order_for_process, order_status=OrderStatus.DELIVERED)
        resp = self.move_orders(optimisation_id, route_one.id, points_ids, settings.drivers_map[2],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Can not place new orders in target drivers route', resp.data['detail'])

        settings.drivers_map[2].car.capacity = 4
        settings.drivers_map[2].car.save()
        resp = self.move_orders(optimisation_id, route_one.id, points_ids, settings.drivers_map[2])
        self.assert_moved_orders(resp.json(), route_one.id, 1, points_ids, settings.drivers_map[2], 4)

    def test_move_advanced_existing_driver(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, start_time=(8,), end_time=(11, 30), capacity=15)
        settings.driver(member_id=2, start_hub=1, end_hub=1, start_time=(8,), end_time=(16, 50), capacity=15)

        settings.order(1, '-37.6780953, 145.1290807', driver=1, deliver_after_time=(8, 40), deliver_before_time=(9, 20))
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(3, '-35.5418094, 144.9643013', driver=2,
                       deliver_after_time=(10, 40), deliver_before_time=(15, 10))
        settings.order(4, '-37.9202176, 145.2230781', driver=2, deliver_after_time=(7, 50), deliver_before_time=(9, ))
        settings.order(5, '-37.9202176, 145.2230781', driver=1, deliver_after_time=(9, 40), deliver_before_time=(10, 8))
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        self.assertEqual(0, len(list(filter(None, map(attrgetter('start_time_known_to_customer'), points_one)))))
        resp = self.client.post('{}{}/notify_customers'.format(self.api_url, optimisation_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        self.assertEqual(
            points_one.filter(point_content_type=ContentType.objects.get_for_model(Order)).count(),
            len(list(filter(None, map(attrgetter('start_time_known_to_customer'), points_one))))
        )
        initial_points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))

        # Cant move jobs because of time validations
        points_ids = list(initial_points_ids)
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[2],
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
        points_one[1].point_object.deliver_after -= timedelta(hours=2)
        points_one[1].point_object.deliver_before += timedelta(hours=6)
        points_one[1].point_object.save(update_fields=('deliver_after', 'deliver_before',))
        points_one[2].point_object.deliver_after -= timedelta(hours=2)
        points_one[2].point_object.deliver_before += timedelta(hours=6)
        points_one[2].point_object.save(update_fields=('deliver_after', 'deliver_before',))
        schedule, _ = Schedule.objects.get_or_create(member=settings.drivers_map[2])
        schedule.schedule['constant'][self._day.weekday()]['day_off'] = True
        schedule.save(update_fields=('schedule',))

        points_ids = list(initial_points_ids)
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[2],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Target driver has day off', resp.data['detail'])

        schedule, _ = Schedule.objects.get_or_create(member=settings.drivers_map[2])
        schedule.schedule['constant'][self._day.weekday()]['day_off'] = False
        schedule.schedule['constant'][self._day.weekday()]['end'] = time(hour=23, minute=30)
        schedule.save(update_fields=('schedule',))

        # Successfully move jobs
        date = timezone.now()
        points_ids = list(initial_points_ids)
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[2])
        self.assert_moved_orders(resp.json(), route_one.id, 1, points_ids[:2], settings.drivers_map[2], 4)
        route_two = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[2].id)
        points_jobs = RoutePoint.objects.filter(route=route_two).order_by('number') \
            .filter(point_content_type=ContentType.objects.get_for_model(Order))
        self.assertEqual(len(list(filter(lambda p: p.start_time_known_to_customer != p.start_time, points_jobs))), 3)
        expected_in_log = 'Moved 2 jobs from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        events_resp = self.client.get('/api/v2/new-events/?date_since={}'.format(date.isoformat().replace('+', 'Z')))
        self.assertEqual(len(events_resp.json()['events']), 3)
        self.assertEqual(events_resp.json()['events'][2]['type'], 'routeoptimisation')
        self.assertEqual(events_resp.json()['events'][2]['object_id'], optimisation_id)
        self.assertEqual(events_resp.json()['events'][2]['event'], 'model_changed')

        points_jobs = RoutePoint.objects.filter(route__optimisation_id=optimisation_id).order_by('number') \
            .filter(point_kind=RoutePointKind.DELIVERY)
        self.assertEqual(len(list(filter(lambda p: p.start_time_known_to_customer != p.start_time, points_jobs))), 4)
        resp = self.client.post('{}{}/notify_customers'.format(self.api_url, optimisation_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        points_jobs = RoutePoint.objects.filter(route__optimisation_id=optimisation_id).order_by('number') \
            .filter(point_kind=RoutePointKind.DELIVERY)
        self.assertEqual(len(list(filter(lambda p: p.start_time_known_to_customer != p.start_time, points_jobs))), 0)
        # can't move started
        points_two = RoutePoint.objects.filter(route=route_two).order_by('number')
        points_ids = list(map(attrgetter('id'), points_two.filter(point_kind=RoutePointKind.DELIVERY)))
        order_for_process = RoutePoint.objects.get(id=points_ids[0]).point_object
        self.change_order_status(settings.drivers_map[2], order=order_for_process,
                                 order_status=OrderStatus.IN_PROGRESS)
        resp = self.move_orders(optimisation_id, route_two.id, [points_ids[0]], settings.drivers_map[1],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('You should move only assigned orders', resp.data['detail'])
        self.change_order_status(settings.drivers_map[2], order=order_for_process,
                                 order_status=OrderStatus.DELIVERED)
        resp = self.move_orders(optimisation_id, route_two.id, [points_ids[0]], settings.drivers_map[1],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('You should move only assigned orders', resp.data['detail'])
        # move and recalculate to route with started orders
        # driver has 2 started orders
        # move one order from another driver
        order_for_process = RoutePoint.objects.get(id=points_ids[1]).point_object
        self.change_order_status(settings.drivers_map[2], order=order_for_process,
                                 order_status=OrderStatus.IN_PROGRESS)
        points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:1], settings.drivers_map[2])
        self.assert_moved_orders(resp.json(), route_one.id, 0, points_ids[:1], settings.drivers_map[2], 5)
        route_two = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[2].id)
        points_jobs = RoutePoint.objects.filter(route=route_two).order_by('number') \
            .filter(point_content_type=ContentType.objects.get_for_model(Order))
        # no more than three
        self.assertEqual(len(list(filter(lambda p: p.start_time_known_to_customer != p.start_time, points_jobs))), 3)
        expected_in_log = 'Moved 1 job from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_move_advanced_new_driver(self, push_mock):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=15)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=15)
        settings.driver(member_id=3, capacity=15, start_time=(11,), end_time=(13, 20))
        settings.order(1, '-37.6780953, 145.1290807', driver=1, deliver_before_time=(11, 30))
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(3, '-35.5418094, 144.9643013', driver=2)
        settings.order(4, '-37.9202176, 145.2230781', driver=2)
        settings.order(5, '-37.9202176, 145.2230781', driver=1, deliver_before_time=(11, 30))
        settings.set_start_place(hub=1)
        settings.set_end_place(hub=1)
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        self.assertEqual(DriverRoute.objects.filter(optimisation_id=optimisation_id).count(), 2)

        points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[3],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Can not place new orders in target drivers route', resp.data['detail'])
        points = list(points_one)
        points[1].point_object.deliver_before += timedelta(minutes=20)
        points[1].point_object.save(update_fields=('deliver_before',))
        points[2].point_object.deliver_before += timedelta(minutes=20)
        points[2].point_object.save(update_fields=('deliver_before',))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[3],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        expected_errors = (
            'Point {} is out of delivery window'.format(points[1].point_object.title),
            'Point {} is out of delivery window'.format(points[2].point_object.title),
            'Route time is out of schedule of driver',
        )
        for error_text in expected_errors:
            for error in resp.data['errors']['can_force']:
                if error_text in error:
                    break
            else:
                raise self.failureException('{} is not in errors'.format(error_text))

        # Fix orders and schedule times
        points[1].point_object.deliver_before += timedelta(hours=6)
        points[1].point_object.save(update_fields=('deliver_before',))
        points[2].point_object.deliver_before += timedelta(hours=6)
        points[2].point_object.save(update_fields=('deliver_before',))
        schedule, _ = Schedule.objects.get_or_create(member=settings.drivers_map[3])
        schedule.schedule['constant'][self._day.weekday()]['end'] = time(hour=23, minute=30)
        schedule.save(update_fields=('schedule',))

        push_mock.reset_mock()
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[3])
        self.assert_moved_orders(resp.json(), route_one.id, 1, points_ids[:2], settings.drivers_map[3], 2)
        self.assertEqual(len(resp.json()['routes']), 3)
        expected_in_log = 'Moved 2 jobs from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        self.assertEqual(DriverRoute.objects.filter(optimisation_id=optimisation_id).count(), 3)
        route_three = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[3].id)
        self.assertEqual(push_mock.call_count, 4)
        bulk_assigned_push_sent, bulk_unassigned_push_sent = False, False
        changed_route_msg, new_route_msg = False, False
        for (push_composer,), _ in push_mock.call_args_list:
            if isinstance(push_composer, BulkAssignedMessage):
                bulk_assigned_push_sent = True
                self.assertEqual(push_composer.driver.id, settings.drivers_map[3].id)
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, BulkUnassignedMessage):
                bulk_unassigned_push_sent = True
                self.assertEqual(push_composer.driver.id, settings.drivers_map[1].id)
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, RouteChangedMessage):
                self.assertEqual(push_composer.driver_route.id, route_one.id)
                changed_route_msg = True
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, NewRoutePushMessage):
                self.assertEqual(push_composer.driver_route.id, route_three.id)
                new_route_msg = True
                self.check_push_composer_no_errors(push_composer)
        self.assertTrue(bulk_assigned_push_sent)
        self.assertTrue(bulk_unassigned_push_sent)
        self.assertTrue(changed_route_msg)
        self.assertTrue(new_route_msg)

        push_mock.reset_mock()
        resp = self.move_orders(optimisation_id, route_one.id, [points_ids[2]], settings.drivers_map[3])
        self.assert_moved_orders(resp.json(), route_one.id, 0, [points_ids[2]], settings.drivers_map[3], 3)
        self.assertEqual(len(resp.json()['routes']), 2)
        expected_in_log = 'Moved 1 job from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        self.assertEqual(push_mock.call_count, 4)
        assigned_push_sent, unassigned_push_sent = False, False
        changed_route_msg_1, changed_route_msg_3 = False, False
        for (push_composer,), _ in push_mock.call_args_list:
            if isinstance(push_composer, AssignedMessage):
                self.assertEqual(push_composer.driver.id, settings.drivers_map[3].id)
                assigned_push_sent = True
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, UnassignedMessage):
                self.assertEqual(push_composer.driver.id, settings.drivers_map[1].id)
                unassigned_push_sent = True
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, RouteChangedMessage):
                if push_composer.driver_route.id == route_one.id:
                    changed_route_msg_1 = True
                if push_composer.driver_route.id == route_three.id:
                    changed_route_msg_3 = True
                self.check_push_composer_no_errors(push_composer)
        self.assertTrue(assigned_push_sent)
        self.assertTrue(unassigned_push_sent)
        self.assertTrue(changed_route_msg_1)
        self.assertTrue(changed_route_msg_3)

    def test_move_advanced_new_driver_handle_errors(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=15)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=15)
        settings.driver(member_id=3, start_hub=1, end_hub=1, capacity=15, start_time=(18, 10), end_time=(22, 20))
        settings.order(1, '-37.6780953, 145.1290807', driver=1)
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(3, '-35.5418094, 144.9643013', driver=2)
        settings.order(4, '-37.9202176, 145.2230781', driver=2)
        settings.order(5, '-37.9202176, 145.2230781', driver=1)
        settings.set_working_hours((8,), (18,))
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        self.assertEqual(DriverRoute.objects.filter(optimisation_id=optimisation_id).count(), 2)

        points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[3],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Driver  is unavailable during the Optimisation working hours', resp.data['detail'])

    def test_move_solo_with_location(self):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.location('-37.869197,144.820283', 1)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.hub('-37.926451, 144.998992', hub_id=2)
        settings.driver(member_id=1, end_hub=1, capacity=15)
        settings.driver(member_id=2, end_hub=2, capacity=15)
        settings.order(1, '-37.6780953, 145.1290807', driver=1)
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(5, '-37.9202176, 145.2230781', driver=1)
        settings.set_start_place(location=1)
        settings.initiator_driver = settings.drivers_map[1]
        settings.initiator_driver_setting = settings.drivers_setting_map[1]

        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_solo_optimisation(settings, expectation)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')

        points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[2])
        self.assert_moved_orders(resp.json(), route_one.id, 1, points_ids[:2], settings.drivers_map[2], 2)
        expected_in_log = 'Moved 2 jobs from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_move_solo(self, push_mock):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=15)
        settings.driver(member_id=2, capacity=15, start_time=(11,), end_time=(13, 20))
        settings.order(1, '-37.6780953, 145.1290807', driver=1, deliver_before_time=(11, 30))
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(5, '-37.9202176, 145.2230781', driver=1, deliver_before_time=(11, 30))
        settings.initiator_driver = settings.drivers_map[1]
        settings.initiator_driver_setting = settings.drivers_setting_map[1]
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_solo_optimisation(settings, expectation)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')

        points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[2],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn("Driver  hasn't set a default hub.", resp.data['detail'])
        settings.drivers_map[2].starting_hub_id = settings.hubs_map[1].id
        settings.drivers_map[2].save(update_fields=('starting_hub_id',))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[2],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn("Driver  hasn't set a default hub.", resp.data['detail'])
        settings.drivers_map[2].ending_hub_id = settings.hubs_map[1].id
        settings.drivers_map[2].save(update_fields=('ending_hub_id',))

        points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[2],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        self.assertIn('Can not place new orders in target drivers route', resp.data['detail'])
        points = list(points_one)
        points[1].point_object.deliver_before += timedelta(minutes=20)
        points[1].point_object.save(update_fields=('deliver_before',))
        points[2].point_object.deliver_before += timedelta(minutes=20)
        points[2].point_object.save(update_fields=('deliver_before',))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[2],
                                expected_status=status.HTTP_400_BAD_REQUEST)
        expected_errors = (
            'Point {} is out of delivery window'.format(points[1].point_object.title),
            'Point {} is out of delivery window'.format(points[2].point_object.title),
            'Route time is out of schedule of driver',
        )
        for error_text in expected_errors:
            for error in resp.data['errors']['can_force']:
                if error_text in error:
                    break
            else:
                raise self.failureException('{} is not in errors'.format(error_text))

        # Fix orders and schedule times
        points[1].point_object.deliver_before += timedelta(hours=6)
        points[1].point_object.save(update_fields=('deliver_before',))
        points[2].point_object.deliver_before += timedelta(hours=6)
        points[2].point_object.save(update_fields=('deliver_before',))
        schedule, _ = Schedule.objects.get_or_create(member=settings.drivers_map[2])
        schedule.schedule['constant'][self._day.weekday()]['end'] = time(hour=23, minute=30)
        schedule.save(update_fields=('schedule',))

        push_mock.reset_mock()
        points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[2])
        self.assert_moved_orders(resp.json(), route_one.id, 1, points_ids[:2], settings.drivers_map[2], 2)
        expected_in_log = 'Moved 2 jobs from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))

        self.assertEqual(DriverRoute.objects.filter(driver_id=settings.drivers_map[2].id).count(), 1)
        route_two = DriverRoute.objects.get(driver_id=settings.drivers_map[2].id)
        resp = self.get_optimisation(route_two.optimisation_id)
        expected_in_log = 'Moved 2 jobs from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        expected_in_log = 'Optimisation created after moving jobs from another driver by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        resp = self.client.get(self.api_url)
        ids = list(map(lambda x: x['id'], resp.data['results']))
        self.assertEqual(resp.data['count'], 2)
        self.assertIn(route_two.optimisation_id, ids)
        self.assertIn(optimisation_id, ids)
        for optimisation_data in resp.data['results']:
            if optimisation_data['id'] == route_two.optimisation_id:
                self.assertEqual(len(optimisation_data['routes']), 1)
            if optimisation_data['id'] == optimisation_id:
                self.assertEqual(len(optimisation_data['routes']), 1)

        self.assertEqual(push_mock.call_count, 4)
        bulk_assigned_push_sent, bulk_unassigned_push_sent = False, False
        changed_route_msg, new_route_msg = False, False
        for (push_composer,), _ in push_mock.call_args_list:
            if isinstance(push_composer, BulkAssignedMessage):
                bulk_assigned_push_sent = True
                self.assertEqual(push_composer.driver.id, settings.drivers_map[2].id)
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, BulkUnassignedMessage):
                bulk_unassigned_push_sent = True
                self.assertEqual(push_composer.driver.id, settings.drivers_map[1].id)
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, RouteChangedMessage):
                self.assertEqual(push_composer.driver_route.id, route_one.id)
                changed_route_msg = True
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, NewRoutePushMessage):
                self.assertEqual(push_composer.driver_route.id, route_two.id)
                new_route_msg = True
                self.check_push_composer_no_errors(push_composer)
        self.assertTrue(bulk_assigned_push_sent)
        self.assertTrue(bulk_unassigned_push_sent)
        self.assertTrue(changed_route_msg)
        self.assertTrue(new_route_msg)

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_move_all_orders_solo(self, push_mock):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=15)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=15)
        settings.order(1, '-37.6780953, 145.1290807', driver=1)
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(5, '-37.9202176, 145.2230781', driver=1)
        settings.initiator_driver = settings.drivers_map[1]
        settings.initiator_driver_setting = settings.drivers_setting_map[1]
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_solo_optimisation(settings, expectation)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')

        push_mock.reset_mock()
        points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:], settings.drivers_map[2])
        self.assert_moved_orders(resp.json(), route_one.id, 0, points_ids[:], settings.drivers_map[2], 2)
        self.assertEqual(resp.json()['state'], RouteOptimisation.STATE.FINISHED)
        expected_in_log = 'Moved 3 jobs from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))

        self.assertEqual(DriverRoute.objects.filter(driver_id=settings.drivers_map[2].id).count(), 1)
        route_two = DriverRoute.objects.get(driver_id=settings.drivers_map[2].id)
        resp = self.get_optimisation(route_two.optimisation_id)
        expected_in_log = 'Moved 3 jobs from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        expected_in_log = 'Optimisation created after moving jobs from another driver by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        resp = self.client.get(self.api_url)
        ids = list(map(lambda x: x['id'], resp.data['results']))
        self.assertEqual(resp.data['count'], 2)
        self.assertIn(route_two.optimisation_id, ids)
        self.assertIn(optimisation_id, ids)
        for optimisation_data in resp.data['results']:
            if optimisation_data['id'] == route_two.optimisation_id:
                self.assertEqual(len(optimisation_data['routes']), 1)
            if optimisation_data['id'] == optimisation_id:
                self.assertEqual(len(optimisation_data['routes']), 0)

        self.assertEqual(push_mock.call_count, 4)
        bulk_assigned_push_sent, bulk_unassigned_push_sent = False, False
        changed_route_msg, new_route_msg = False, False
        for (push_composer,), _ in push_mock.call_args_list:
            if isinstance(push_composer, BulkAssignedMessage):
                bulk_assigned_push_sent = True
                self.assertEqual(push_composer.driver.id, settings.drivers_map[2].id)
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, BulkUnassignedMessage):
                bulk_unassigned_push_sent = True
                self.assertEqual(push_composer.driver.id, settings.drivers_map[1].id)
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, RouteChangedMessage):
                self.assertEqual(push_composer.driver_route.id, route_one.id)
                changed_route_msg = True
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, NewRoutePushMessage):
                self.assertEqual(push_composer.driver_route.id, route_two.id)
                new_route_msg = True
                self.check_push_composer_no_errors(push_composer)
        self.assertTrue(bulk_assigned_push_sent)
        self.assertTrue(bulk_unassigned_push_sent)
        self.assertTrue(changed_route_msg)
        self.assertTrue(new_route_msg)

    def test_move_advanced_new_driver_and_existing_with_break(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.hub('-37.926451, 144.998992', hub_id=2)
        settings.driver(member_id=1, start_hub=1, end_hub=2, capacity=15,
                        breaks=[DriverBreakSetting((9, 0), (9, 30), 15)])
        settings.driver(member_id=2, start_hub=1, end_hub=2, capacity=15,
                        breaks=[DriverBreakSetting((9, 0), (9, 30), 15)])
        settings.order(1, '-37.6780953, 145.1290807', driver=1)
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(3, '-35.5418094, 144.9643013', driver=2)
        settings.order(4, '-37.9202176, 145.2230781', driver=2)
        settings.order(5, '-37.9202176, 145.2230781', driver=1)
        settings.set_start_place(hub=1)
        settings.set_end_place(hub=2)
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)
        self.assertEqual(DriverRoute.objects.filter(optimisation_id=optimisation_id).count(), 2)
        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        route_two = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[2].id)
        points_two = RoutePoint.objects.filter(route=route_two).order_by('number')

        settings.driver(member_id=3, start_hub=1, end_hub=2, capacity=15,
                        breaks=[DriverBreakSetting((9, 50), (10, 0), 5)])
        points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:2], settings.drivers_map[3])
        self.assert_moved_orders(resp.json(), route_one.id, 1, points_ids[:2], settings.drivers_map[3], 2)
        self.assertEqual(len(resp.json()['routes']), 3)
        expected_in_log = 'Moved 2 jobs from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        self.assertEqual(DriverRoute.objects.filter(optimisation_id=optimisation_id).count(), 3)
        route_three = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[3].id)
        self.assertEqual(RoutePoint.objects.filter(route=route_one).count(), 4)
        self.assertEqual(RoutePoint.objects.filter(route=route_two).count(), 5)
        self.assertEqual(RoutePoint.objects.filter(route=route_three).count(), 5)

        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.DELIVERY, '08:42:12', '08:52:12'),
            (RoutePointKind.BREAK, '08:52:12', '09:22:12'),
            (RoutePointKind.HUB, '09:22:12', '09:22:12'),
        )
        get = self.client.get(self.api_url + str(optimisation_id))
        route_data = list(filter(lambda x: x['id'] == route_one.id, get.json()['routes']))[0]
        for point, point_kind_time in zip(route_data['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')

        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.BREAK, '09:00:00', '09:30:00'),
            (RoutePointKind.DELIVERY, '12:02:37', '12:12:37'),
            (RoutePointKind.DELIVERY, '15:59:47', '16:09:47'),
            (RoutePointKind.HUB, '16:47:49', '16:47:49'),
        )
        get = self.client.get(self.api_url + str(optimisation_id))
        route_data = list(filter(lambda x: x['id'] == route_two.id, get.json()['routes']))[0]
        for point, point_kind_time in zip(route_data['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')

        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.DELIVERY, '08:42:56', '08:52:56'),
            (RoutePointKind.BREAK, '09:33:41', '09:55:00'),
            (RoutePointKind.DELIVERY, '09:55:00', '10:05:00'),
            (RoutePointKind.HUB, '10:43:02', '10:43:02'),
        )
        get = self.client.get(self.api_url + str(optimisation_id))
        for point, point_kind_time in zip(get.json()['routes'][2]['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')

        points_ids = list(map(attrgetter('id'), points_two.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_two.id, [points_ids[1]], settings.drivers_map[3])
        self.assert_moved_orders(resp.json(), route_two.id, 1, [points_ids[1]], settings.drivers_map[3], 3)
        self.assertEqual(len(resp.json()['routes']), 3)
        expected_in_log = 'Moved 1 job from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        self.assertEqual(RoutePoint.objects.filter(route=route_two).count(), 4)
        self.assertEqual(RoutePoint.objects.filter(route=route_three).count(), 6)

        get = self.client.get(self.api_url + str(optimisation_id))
        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.BREAK, '09:00:00', '09:30:00'),
            (RoutePointKind.DELIVERY, '12:02:37', '12:12:37'),
            (RoutePointKind.HUB, '15:57:13', '15:57:13'),
        )
        for point, point_kind_time in zip(get.json()['routes'][1]['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')
        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.DELIVERY, '08:42:56', '08:52:56'),
            (RoutePointKind.BREAK, '09:33:41', '09:55:00'),
            (RoutePointKind.DELIVERY, '09:55:00', '10:05:00'),
            (RoutePointKind.DELIVERY, '10:05:00', '10:15:00'),
            (RoutePointKind.HUB, '10:53:02', '10:53:02'),
        )
        for point, point_kind_time in zip(get.json()['routes'][2]['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')

        points_three = RoutePoint.objects.filter(route=route_three).order_by('number')
        points_ids = list(map(attrgetter('id'), points_three.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_three.id, [points_ids[1]], settings.drivers_map[2])
        self.assert_moved_orders(resp.json(), route_three.id, 2, [points_ids[1]], settings.drivers_map[2], 2)
        self.assertEqual(RoutePoint.objects.filter(route=route_two).count(), 5)
        self.assertEqual(RoutePoint.objects.filter(route=route_three).count(), 5)

        get = self.client.get(self.api_url + str(optimisation_id))
        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.BREAK, '09:00:00', '09:30:00'),
            (RoutePointKind.DELIVERY, '12:02:37', '12:12:37'),
            (RoutePointKind.DELIVERY, '15:59:47', '16:09:47'),
            (RoutePointKind.HUB, '16:47:49', '16:47:49'),
        )
        for point, point_kind_time in zip(get.json()['routes'][1]['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')
        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.DELIVERY, '08:42:56', '08:52:56'),
            (RoutePointKind.DELIVERY, '09:33:41', '09:43:41'),
            (RoutePointKind.BREAK, '09:50:00', '10:00:00'),
            (RoutePointKind.HUB, '10:31:43', '10:31:43'),
        )
        for point, point_kind_time in zip(get.json()['routes'][2]['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')

        # Final check
        resp = self.client.get(self.api_url)
        ids = list(map(lambda x: x['id'], resp.data['results']))
        self.assertEqual(resp.data['count'], 1)
        self.assertIn(optimisation_id, ids)
        for optimisation_data in resp.data['results']:
            if optimisation_data['id'] == optimisation_id:
                self.assertEqual(len(optimisation_data['routes']), 3)

    def test_move_all_orders_solo_with_break(self):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.hub('-37.926451, 144.998992', hub_id=2)
        settings.driver(member_id=1, start_hub=1, end_hub=2, capacity=15,
                        breaks=[DriverBreakSetting((9, 30), (10, 0), 15)])
        settings.driver(member_id=2, start_hub=1, end_hub=2, capacity=15,
                        breaks=[DriverBreakSetting((8, 10), (8, 20), 5)])
        settings.driver(member_id=3, start_hub=1, end_hub=2, capacity=15,
                        breaks=[DriverBreakSetting((8, 30), (8, 40), 5)])
        settings.order(1, '-37.6780953, 145.1290807', driver=1)
        settings.order(2, '-37.926451, 144.998992', driver=1)
        settings.order(5, '-37.9202176, 145.2230781', driver=1)
        settings.initiator_driver = settings.drivers_map[1]
        settings.initiator_driver_setting = settings.drivers_setting_map[1]
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_solo_optimisation(settings, expectation)

        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.DELIVERY, '08:42:56', '08:52:56'),
            (RoutePointKind.BREAK, '09:30:00', '10:00:00'),
            (RoutePointKind.DELIVERY, '10:03:41', '10:13:41'),
            (RoutePointKind.DELIVERY, '10:51:43', '11:01:43'),
            (RoutePointKind.HUB, '11:01:43', '11:01:43'),
        )
        get = self.client.get(self.api_url + str(optimisation_id))
        for point, point_kind_time in zip(get.json()['routes'][0]['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')

        route_one = DriverRoute.objects.get(optimisation_id=optimisation_id, driver_id=settings.drivers_map[1].id)
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        self.assertEqual(RoutePoint.objects.filter(route=route_one).count(), 6)

        points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:1], settings.drivers_map[2])
        self.assert_moved_orders(resp.json(), route_one.id, 2, points_ids[:1], settings.drivers_map[2], 1)
        self.assertEqual(resp.json()['state'], RouteOptimisation.STATE.COMPLETED)
        expected_in_log = 'Moved 1 job from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.DELIVERY, '08:47:50', '08:57:50'),
            (RoutePointKind.BREAK, '09:30:00', '10:00:00'),
            (RoutePointKind.DELIVERY, '10:05:52', '10:15:52'),
            (RoutePointKind.HUB, '10:15:52', '10:15:52'),
        )
        get = self.client.get(self.api_url + str(optimisation_id))
        for point, point_kind_time in zip(get.json()['routes'][0]['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')

        self.assertEqual(DriverRoute.objects.filter(driver_id=settings.drivers_map[2].id).count(), 1)
        route_two = DriverRoute.objects.get(driver_id=settings.drivers_map[2].id)
        self.assertEqual(RoutePoint.objects.filter(route=route_one).count(), 5)
        self.assertEqual(RoutePoint.objects.filter(route=route_two).count(), 4)
        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.BREAK, '08:10:00', '08:20:00'),
            (RoutePointKind.DELIVERY, '08:52:56', '09:02:56'),
            (RoutePointKind.HUB, '09:56:32', '09:56:32'),
        )
        get = self.get_optimisation(route_two.optimisation_id)
        for point, point_kind_time in zip(get.json()['routes'][0]['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')
        expected_in_log = 'Moved 1 job from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], get.json()['log']['messages'])))
        expected_in_log = 'Optimisation created after moving jobs from another driver by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], get.json()['log']['messages'])))

        # from first to third
        points_one = RoutePoint.objects.filter(route=route_one).order_by('number')
        points_ids = list(map(attrgetter('id'), points_one.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(optimisation_id, route_one.id, points_ids[:], settings.drivers_map[3])
        self.assert_moved_orders(resp.json(), route_one.id, 0, points_ids[:], settings.drivers_map[3], 3)
        self.assertEqual(resp.json()['state'], RouteOptimisation.STATE.FINISHED)
        expected_in_log = 'Moved 2 jobs from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        self.assertEqual(RoutePoint.objects.filter(route=route_one).count(), 0)

        self.assertEqual(DriverRoute.objects.filter(driver_id=settings.drivers_map[3].id).count(), 1)
        route_three = DriverRoute.objects.get(driver_id=settings.drivers_map[3].id)
        self.assertEqual(RoutePoint.objects.filter(route=route_three).count(), 5)
        point_kind_times = (
            (RoutePointKind.HUB, '08:00:00', '08:00:00'),
            (RoutePointKind.BREAK, '08:30:00', '08:40:00'),
            (RoutePointKind.DELIVERY, '08:57:50', '09:07:50'),
            (RoutePointKind.DELIVERY, '09:45:52', '09:55:52'),
            (RoutePointKind.HUB, '09:55:52', '09:55:52'),
        )
        get = self.get_optimisation(route_three.optimisation_id)
        for point, point_kind_time in zip(get.json()['routes'][0]['points'], point_kind_times):
            self.assertEqual(point['point_kind'], point_kind_time[0])
            self.assertEqual(point['start_time'], f'{str(self._day)}T{point_kind_time[1]}+10:00')
            self.assertEqual(point['end_time'], f'{str(self._day)}T{point_kind_time[2]}+10:00')
        expected_in_log = 'Moved 2 jobs from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], get.json()['log']['messages'])))
        expected_in_log = 'Optimisation created after moving jobs from another driver by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], get.json()['log']['messages'])))

        # from second to third
        points_two = RoutePoint.objects.filter(route=route_two).order_by('number')
        points_ids = list(map(attrgetter('id'), points_two.filter(point_kind=RoutePointKind.DELIVERY)))
        resp = self.move_orders(route_two.optimisation_id, route_two.id, points_ids[:], settings.drivers_map[3])
        self.assert_moved_orders(resp.json(), route_two.id, 0, points_ids[:], settings.drivers_map[3], 3)
        self.assertEqual(resp.json()['state'], RouteOptimisation.STATE.FINISHED)
        expected_in_log = 'Moved 1 job from route of driver  to route of driver  by '
        self.assertIn(expected_in_log, list(map(lambda x: x['text'], resp.json()['log']['messages'])))
        self.assertEqual(RoutePoint.objects.filter(route=route_two).count(), 0)

        # Final check
        resp = self.client.get(self.api_url)
        ids = list(map(lambda x: x['id'], resp.data['results']))
        self.assertEqual(resp.data['count'], 4)
        self.assertIn(route_two.optimisation_id, ids)
        self.assertIn(route_three.optimisation_id, ids)
        self.assertIn(optimisation_id, ids)
        for optimisation_data in resp.data['results']:
            if optimisation_data['id'] == route_three.optimisation_id:
                self.assertEqual(len(optimisation_data['routes']), 1)
            if optimisation_data['id'] == route_two.optimisation_id:
                self.assertEqual(len(optimisation_data['routes']), 0)
            if optimisation_data['id'] == optimisation_id:
                self.assertEqual(len(optimisation_data['routes']), 0)

    def assert_moved_orders(self, resp, route_id, from_driver_count, points_ids, target_driver, target_driver_count):
        ord_ids = RoutePoint.objects.filter(id__in=points_ids).values_list('point_object_id', flat=True)
        self.assertEqual(Order.aggregated_objects.filter(id__in=ord_ids, driver_id=target_driver.id).count(),
                         len(points_ids))
        for route in resp['routes']:
            if route['id'] == route_id:
                self.assertEqual(route['orders_count'], from_driver_count)
            if 'driver' in route and route['driver']['id'] == target_driver.id:
                self.assertEqual(route['orders_count'], target_driver_count)
            if 'driver_id' in route and route['driver_id'] == target_driver.id:
                self.assertEqual(route['orders_count'], target_driver_count)
        if from_driver_count == 0:
            self.assertFalse(DriverRoute.objects.filter(id=route_id).exists())

    def move_orders(self, optimisation_id, route_id, points_ids, target_driver,
                    expected_status=status.HTTP_200_OK, force=False):
        distance_matrix_cache = TestDiMaCache()
        pp_distance_matrix_cache = TestDiMaCache(polylines=True)
        path = 'route_optimisation.utils.managing.move_orders_preparing.MoveOrderPrepareService.' \
               'get_distance_matrix_cache'
        pp_path = 'route_optimisation.utils.managing.move_orders_preparing.MoveOrderPrepareService.' \
                  'get_pp_distance_matrix_cache'
        with mock.patch(path, return_value=distance_matrix_cache), \
                mock.patch(pp_path, return_value=pp_distance_matrix_cache):
            resp = self.client.post('{}{}/move_orders'.format(self.api_url, optimisation_id), {
                'route': route_id,
                'points': points_ids,
                'target_driver': target_driver.id,
                'force': force,
            })
        self.assertEqual(resp.status_code, expected_status)
        return resp

    def change_order_status(self, driver, order, order_status):
        self.client.force_authenticate(driver)
        resp = self.client.put('{url}{id}/status/'.format(url=self.orders_url, id=order.id), {'status': order_status})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.manager)
