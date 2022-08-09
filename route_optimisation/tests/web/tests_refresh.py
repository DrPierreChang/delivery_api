from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from notification.tests.mixins import NotificationTestMixin
from route_optimisation.const import OPTIMISATION_TYPES, RoutePointKind
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

from ...models import DriverRoute, RouteOptimisation
from ...push_messages.composers import RouteChangedMessage, SoloOptimisationStatusChangeMessage
from ..test_utils.setting import DriverBreakSetting
from .api_settings import SoloAPISettings
from .mixins import ORToolsMixin
from .optimisation_expectation import (
    LogCheck,
    NumberFieldConsecutiveCheck,
    OptimisationExpectation,
    RoutePointsCountCheck,
)
from .tests_concatenated_orders import enable_concatenated_orders_for_merchant
from .tests_pickup_feature import enable_pickup_for_merchant


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class RefreshSoloOptimisationTestCase(NotificationTestMixin, ORToolsMixin, APITestCase):
    @enable_pickup_for_merchant
    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_refresh(self, push_mock):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.driver(member_id=2, start_hub=1, end_hub=1, end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.698763,145.054753', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.initiator_driver = settings.drivers_map[2]
        settings.initiator_driver_setting = settings.drivers_setting_map[2]
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('3 jobs were included into Optimisation', partly=True))
        opt_id = self.run_solo_optimisation(settings, expected)

        self.client.force_authenticate(settings.drivers_map[2])
        get = self.get_legacy_driver_routes(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 3)
        route = DriverRoute.objects.get(optimisation__id=opt_id, driver__id=settings.drivers_map[2].id)
        route_points = route.points.all().order_by('number')
        n = 4
        for point in route_points[:n]:
            if point.point_kind == RoutePointKind.PICKUP:
                self.change_status_to(point.point_object, OrderStatus.PICK_UP)
                self.change_status_to(point.point_object, OrderStatus.PICKED_UP)
            if point.point_kind == RoutePointKind.DELIVERY:
                self.change_status_to(point.point_object, OrderStatus.IN_PROGRESS)
                self.change_status_to(point.point_object, OrderStatus.DELIVERED)

        settings.order(3, '-37.8238154,145.0108082', pickup_address='-37.5795883,143.8387151', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        push_mock.reset_mock()
        expected = OptimisationExpectation(skipped_orders=0, response_status=status.HTTP_200_OK)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('Optimisation refresh started', partly=True))
        expected.add_check(LogCheck('Optimisation refresh completed', partly=True))
        expected.add_check(LogCheck('1 job was included into Optimisation', partly=True))
        date = timezone.now()
        self.refresh_solo(opt_id, route.id, settings, expected)
        # check in route
        ord_ = Order.objects.get(id=settings.orders_map[3].id)
        driver_route = ord_.route_points.all().first().route
        self.assertEqual(driver_route.driver_id, settings.drivers_map[2].id)
        self.assertEqual(driver_route.optimisation_id, opt_id)
        # check push about changed route
        self.assertEqual(push_mock.call_count, 1)
        push_composer = push_mock.call_args_list[0][0][0]
        self.assertTrue(isinstance(push_composer, RouteChangedMessage))
        self.assertEqual(push_composer.driver_route.driver_id, settings.drivers_map[2].id)
        self.assertEqual(push_composer.optimisation.id, opt_id)
        self.check_push_composer_no_errors(push_composer)
        # check events
        self.client.force_authenticate(self.manager)
        events_resp = self.client.get('/api/v2/new-events/?date_since={}'.format(date.isoformat().replace('+', 'Z')))
        self.assertEqual(len(events_resp.json()['events']), 2)
        self.assertEqual(events_resp.json()['events'][0]['type'], 'routeoptimisation')
        self.assertEqual(events_resp.json()['events'][0]['object_id'], opt_id)
        self.assertEqual(events_resp.json()['events'][0]['event'], 'model_changed')

    @enable_pickup_for_merchant
    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_refresh_with_breaks_and_required_start_sequence(self, push_mock):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.driver(member_id=2, start_hub=1, end_hub=1, end_time=(18, 0), capacity=15,
                        breaks=[DriverBreakSetting((10, 30), (10, 40), 5)])
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.698763,145.054753', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.initiator_driver = settings.drivers_map[2]
        settings.initiator_driver_setting = settings.drivers_setting_map[2]
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(RoutePointsCountCheck(settings.drivers_map[2].id, 7, hubs=2,
                                                 pickups=1, deliveries=3, breaks=1))
        expected.add_check(LogCheck('3 jobs were included into Optimisation', partly=True))
        opt_id = self.run_solo_optimisation(settings, expected)

        self.client.force_authenticate(settings.drivers_map[2])
        get = self.get_legacy_driver_routes(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 3)
        route = DriverRoute.objects.get(optimisation__id=opt_id, driver__id=settings.drivers_map[2].id)
        route_points = route.points.all().order_by('number')
        n = 5
        for point in route_points[:n]:
            if point.point_kind == RoutePointKind.PICKUP:
                self.change_status_to(point.point_object, OrderStatus.PICK_UP)
                self.change_status_to(point.point_object, OrderStatus.PICKED_UP)
            if point.point_kind == RoutePointKind.DELIVERY:
                self.change_status_to(point.point_object, OrderStatus.IN_PROGRESS)
                self.change_status_to(point.point_object, OrderStatus.DELIVERED)

        settings.order(3, '-37.8238154,145.0108082', pickup_address='-37.5795883,143.8387151', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        push_mock.reset_mock()
        expected = OptimisationExpectation(skipped_orders=0, response_status=status.HTTP_200_OK)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(RoutePointsCountCheck(settings.drivers_map[2].id, 9, hubs=2,
                                                 pickups=2, deliveries=4, breaks=1))
        expected.add_check(LogCheck('Optimisation refresh started', partly=True))
        expected.add_check(LogCheck('Optimisation refresh completed', partly=True))
        expected.add_check(LogCheck('1 job was included into Optimisation', partly=True))
        self.refresh_solo(opt_id, route.id, settings, expected)

    @enable_pickup_for_merchant
    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_refresh_with_breaks(self, push_mock):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.driver(member_id=2, start_hub=1, end_hub=1, end_time=(18, 0), capacity=15,
                        breaks=[DriverBreakSetting((11, 30), (11, 40), 5)])
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.698763,145.054753', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.initiator_driver = settings.drivers_map[2]
        settings.initiator_driver_setting = settings.drivers_setting_map[2]
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(RoutePointsCountCheck(settings.drivers_map[2].id, 7, hubs=2,
                                                 pickups=1, deliveries=3, breaks=1))
        expected.add_check(LogCheck('3 jobs were included into Optimisation', partly=True))
        opt_id = self.run_solo_optimisation(settings, expected)
        route = DriverRoute.objects.get(optimisation__id=opt_id, driver__id=settings.drivers_map[2].id)
        self.assertEqual(route.points.count(), 8)

        settings.order(3, '-37.8238154,145.0108082', pickup_address='-37.5795883,143.8387151', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        push_mock.reset_mock()
        expected = OptimisationExpectation(skipped_orders=0, response_status=status.HTTP_200_OK)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(RoutePointsCountCheck(settings.drivers_map[2].id, 9, hubs=2,
                                                 pickups=2, deliveries=4, breaks=1))
        expected.add_check(LogCheck('Optimisation refresh started', partly=True))
        expected.add_check(LogCheck('Optimisation refresh completed', partly=True))
        expected.add_check(LogCheck('1 job was included into Optimisation', partly=True))
        self.refresh_solo(opt_id, route.id, settings, expected)

    @enable_pickup_for_merchant
    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_refresh_with_location(self, push_mock):
        settings = SoloAPISettings(
            OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone, self.merchant, self.manager,
        )
        settings.location('-37.869197,144.82028300000002', 1)
        settings.location('-37.7855699,144.84063459999993', 2)
        settings.set_start_place(location=1)
        settings.set_end_place(location=2)
        settings.driver(member_id=2, start_location=1, end_location=1, end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', driver=2, deliver_after_time=(9, 50,),
                       deliver_before_time=(19, 0))
        settings.initiator_driver = settings.drivers_map[2]
        settings.initiator_driver_setting = settings.drivers_setting_map[2]

        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('1 job was included into Optimisation', partly=True))
        opt_id = self.run_solo_optimisation(settings, expected)
        route = DriverRoute.objects.get(optimisation__id=opt_id, driver__id=settings.drivers_map[2].id)
        self.assertEqual(route.points.count(), 3)

        settings.order(3, '-37.8238154,145.0108082', driver=2, deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        push_mock.reset_mock()
        expected = OptimisationExpectation(skipped_orders=0, response_status=status.HTTP_200_OK)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('Optimisation refresh started', partly=True))
        expected.add_check(LogCheck('Optimisation refresh completed', partly=True))
        expected.add_check(LogCheck('1 job was included into Optimisation', partly=True))
        self.refresh_solo(opt_id, route.id, settings, expected)
        self.assertEqual(route.points.count(), 4)

    @enable_pickup_for_merchant
    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_refresh_jobs_not_added(self, push_mock):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.driver(member_id=2, start_hub=1, end_hub=1, end_time=(15, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.698763,145.054753', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.initiator_driver = settings.drivers_map[2]
        settings.initiator_driver_setting = settings.drivers_setting_map[2]
        self.client.force_authenticate(settings.drivers_map[2])
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('3 jobs were included into Optimisation', partly=True))
        opt_id = self.run_solo_optimisation(settings, expected)
        route = DriverRoute.objects.get(optimisation__id=opt_id, driver__id=settings.drivers_map[2].id)
        self.client.force_authenticate(settings.drivers_map[2])
        get = self.get_legacy_driver_routes(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 3)

        settings.order(3, '-37.8238154,145.0108082', pickup_address='-37.5795883,143.8387151', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        push_mock.reset_mock()
        expected = OptimisationExpectation(skipped_orders=1, response_status=status.HTTP_200_OK)
        self.refresh_solo(opt_id, route.id, settings, expected)
        # check order not added to route
        ord_ = Order.objects.get(id=settings.orders_map[3].id)
        self.assertIsNone(ord_.route_points.all().first())
        self.assertEqual(DriverRoute.objects.get(driver_id=settings.drivers_map[2].id).points.count(), 7)
        self.assertEqual(push_mock.call_count, 1)
        push_composer = push_mock.call_args_list[0][0][0]
        self.assertTrue(isinstance(push_composer, RouteChangedMessage))
        self.assertEqual(push_composer.driver_route.driver_id, settings.drivers_map[2].id)
        self.assertEqual(push_composer.optimisation.id, opt_id)
        self.check_push_composer_no_errors(push_composer)

    @enable_pickup_for_merchant
    def test_no_refresh_in_case_nothing_changed(self):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.driver(member_id=2, start_hub=1, end_hub=1, end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.698763,145.054753', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.initiator_driver = settings.drivers_map[2]
        settings.initiator_driver_setting = settings.drivers_setting_map[2]
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('3 jobs were included into Optimisation', partly=True))
        opt_id = self.run_solo_optimisation(settings, expected)
        route = DriverRoute.objects.get(optimisation__id=opt_id, driver__id=settings.drivers_map[2].id)
        self.client.force_authenticate(settings.drivers_map[2])
        get = self.get_legacy_driver_routes(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 3)
        # http code 400 because nothing changed
        expected = OptimisationExpectation(response_status=status.HTTP_400_BAD_REQUEST)
        expected.add_check(LogCheck('Optimisation refresh started', partly=True))
        expected.add_check(LogCheck('Nothing to refresh. Everything is already optimised', partly=True))
        expected.add_check(LogCheck('Optimisation refresh failed', partly=True))
        self.refresh_solo(opt_id, route.id, settings, expected)

        # Add new job and refresh
        settings.order(3, '-37.8238154,145.0108082', pickup_address='-37.5795883,143.8387151', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        self.client.force_authenticate(settings.drivers_map[2])
        expected = OptimisationExpectation(skipped_orders=0, response_status=status.HTTP_200_OK)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('Optimisation refresh started', partly=True))
        expected.add_check(LogCheck('Optimisation refresh completed', partly=True))
        expected.add_check(LogCheck('1 job was included into Optimisation', partly=True))
        self.refresh_solo(opt_id, route.id, settings, expected)
        self.client.force_authenticate(settings.drivers_map[2])
        get = self.get_legacy_driver_routes(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 4)
        # http code 400 because nothing changed
        self.client.force_authenticate(settings.drivers_map[2])
        expected = OptimisationExpectation(response_status=status.HTTP_400_BAD_REQUEST)
        self.refresh_solo(opt_id, route.id, settings, expected)

    @enable_pickup_for_merchant
    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_refresh_changed_delivery_interval(self, push_mock):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.driver(member_id=2, start_hub=1, end_hub=1, end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.698763,145.054753', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.initiator_driver = settings.drivers_map[2]
        settings.initiator_driver_setting = settings.drivers_setting_map[2]
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('3 jobs were included into Optimisation', partly=True))
        opt_id = self.run_solo_optimisation(settings, expected)
        route = DriverRoute.objects.get(optimisation__id=opt_id, driver__id=settings.drivers_map[2].id)
        self.client.force_authenticate(settings.drivers_map[2])
        get = self.get_legacy_driver_routes(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 3)
        self.client.force_authenticate(self.manager)
        resp = self.client.post('{}{}/notify_customers'.format(self.api_url, opt_id))

        # Change deliver interval. Refresh works. Nothing changed.
        order = Order.objects.get(id=settings.orders_map[2].id)
        order.deliver_before -= timedelta(hours=1)
        order.save(update_fields=('deliver_before',))
        self.client.force_authenticate(settings.drivers_map[2])
        expected = OptimisationExpectation(skipped_orders=0, response_status=status.HTTP_200_OK)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('Optimisation refresh started', partly=True))
        expected.add_check(LogCheck('Optimisation refresh completed', partly=True))
        self.refresh_solo(opt_id, route.id, settings, expected)
        self.client.force_authenticate(settings.drivers_map[2])
        get = self.get_legacy_driver_routes(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 3)
        optimisation = RouteOptimisation.objects.get(id=opt_id)
        self.assertTrue(optimisation.customers_notified)

        # Change deliver interval. Refresh works. Ordering of jobs changed.
        order = Order.objects.get(id=settings.orders_map[2].id)
        order.deliver_before -= timedelta(hours=6)
        order.save(update_fields=('deliver_before',))
        self.client.force_authenticate(settings.drivers_map[2])
        expected = OptimisationExpectation(skipped_orders=0, response_status=status.HTTP_200_OK)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('Optimisation refresh started', partly=True))
        expected.add_check(LogCheck('Optimisation refresh completed', partly=True))
        self.refresh_solo(opt_id, route.id, settings, expected)
        self.client.force_authenticate(settings.drivers_map[2])
        get = self.get_legacy_driver_routes(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 3)
        optimisation.refresh_from_db()
        self.assertFalse(optimisation.customers_notified)

        # Change deliver interval.
        # Refresh failed because can not place orders with such delivery intervals.
        order.deliver_before -= timedelta(hours=2)
        order.save(update_fields=('deliver_before',))
        self.client.force_authenticate(settings.drivers_map[2])
        push_mock.reset_mock()
        expected = OptimisationExpectation(skipped_orders=0, response_status=status.HTTP_200_OK)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('Optimisation refresh started', partly=True))
        expected.add_check(LogCheck('No solution was found for this Optimisation', partly=True))
        expected.add_check(LogCheck('Optimisation refresh failed', partly=True))
        self.refresh_solo(opt_id, route.id, settings, expected)
        self.client.force_authenticate(settings.drivers_map[2])
        get = self.get_legacy_driver_routes(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 3)
        self.assertEqual(push_mock.call_count, 1)
        push_composer = push_mock.call_args_list[0][0][0]
        self.assertTrue(isinstance(push_composer, SoloOptimisationStatusChangeMessage))
        self.assertFalse(push_composer.successful)
        self.assertEqual(push_composer.optimisation.id, opt_id)
        self.check_push_composer_no_errors(push_composer)

    @enable_pickup_for_merchant
    @enable_concatenated_orders_for_merchant
    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_refresh_concatenated(self, push_mock):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.driver(member_id=1, start_hub=1, end_hub=1, end_time=(20, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', driver=1, pickup_address='-37.755938,145.706767', capacity=4,
                       deliver_after_time=(7,),)
        settings.order(2, '-37.8421644,144.9399743', driver=1, pickup_address='-37.5795883,143.8387151',
                       deliver_after_time=(7,),)
        settings.order(3, '-37.8421644,144.9399743', driver=1, deliver_after_time=(7,),)
        settings.concatenated_order(4, (1, 2, 3))
        settings.order(5, '-37.8485871,144.6670881', driver=1, pickup_address='-37.698763,145.054753', capacity=2)
        settings.order(6, '-37.698763,145.054753', driver=1)
        settings.set_use_vehicle_capacity(True)
        settings.initiator_driver = settings.drivers_map[1]
        settings.initiator_driver_setting = settings.drivers_setting_map[1]
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('3 jobs were included into Optimisation', partly=True))
        opt_id = self.run_solo_optimisation(settings, expected)

        self.client.force_authenticate(settings.drivers_map[1])
        get = self.get_legacy_driver_routes(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 3)
        route = DriverRoute.objects.get(optimisation__id=opt_id, driver__id=settings.drivers_map[1].id)
        route_points = route.points.all().order_by('number')
        n = 4
        for point in route_points[:n]:
            if point.point_kind == RoutePointKind.PICKUP:
                self.change_status_to(point.point_object, OrderStatus.PICK_UP)
                self.change_status_to(point.point_object, OrderStatus.PICKED_UP)
            if point.point_kind == RoutePointKind.DELIVERY:
                self.change_status_to(point.point_object, OrderStatus.IN_PROGRESS)
                self.change_status_to(point.point_object, OrderStatus.DELIVERED)

        settings.order(7, '-37.8485871,144.6670881', driver=1, pickup_address='-37.755938,145.706767', capacity=2,
                       deliver_after_time=(7,),)
        settings.order(8, '-37.8485871,144.6670881', driver=1, pickup_address='-37.5795883,143.8387151',
                       deliver_after_time=(7,),)
        settings.order(9, '-37.8485871,144.6670881', driver=1, deliver_after_time=(7,),)
        settings.concatenated_order(10, (7, 8, 9))
        push_mock.reset_mock()
        expected = OptimisationExpectation(skipped_orders=0, response_status=status.HTTP_200_OK)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('Optimisation refresh started', partly=True))
        expected.add_check(LogCheck('Optimisation refresh completed', partly=True))
        expected.add_check(LogCheck('1 job was included into Optimisation', partly=True))
        date = timezone.now()
        self.refresh_solo(opt_id, route.id, settings, expected)
        # check in route
        ord_ = Order.aggregated_objects.get(id=settings.orders_map[10].id)
        driver_route = ord_.route_points.all().first().route
        self.assertEqual(driver_route.driver_id, settings.drivers_map[1].id)
        self.assertEqual(driver_route.optimisation_id, opt_id)
        # check push about changed route
        self.assertEqual(push_mock.call_count, 1)
        push_composer = push_mock.call_args_list[0][0][0]
        self.assertTrue(isinstance(push_composer, RouteChangedMessage))
        self.assertEqual(push_composer.driver_route.driver_id, settings.drivers_map[1].id)
        self.assertEqual(push_composer.optimisation.id, opt_id)
        self.check_push_composer_no_errors(push_composer)
        # check events
        self.client.force_authenticate(self.manager)
        events_resp = self.client.get('/api/v2/new-events/?date_since={}'.format(date.isoformat().replace('+', 'Z')))
        self.assertEqual(len(events_resp.json()['events']), 2)
        self.assertEqual(events_resp.json()['events'][0]['type'], 'routeoptimisation')
        self.assertEqual(events_resp.json()['events'][0]['object_id'], opt_id)
        self.assertEqual(events_resp.json()['events'][0]['event'], 'model_changed')

    def change_status_to(self, order, order_status):
        concatenated_orders_url = '/api/mobile/concatenated_orders/v1/'
        data = {'status': order_status}
        if order.concatenated_order_id is not None:
            order_resp = self.client.patch('{}{}'.format(concatenated_orders_url, order.concatenated_order_id), data)
        elif order.is_concatenated_order:
            order_resp = self.client.patch('{}{}'.format(concatenated_orders_url, order.id), data)
        else:
            order_resp = self.client.put('/api/orders/%s/status' % order.order_id, data)
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(order_resp.data['status'], order_status)
