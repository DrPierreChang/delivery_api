from django.test import override_settings

from rest_framework.test import APITestCase

from notification.tests.mixins import NotificationTestMixin
from route_optimisation.const import OPTIMISATION_TYPES
from route_optimisation.push_messages.composers import NewRoutePushMessage, SoloOptimisationStatusChangeMessage
from route_optimisation.tests.web.api_settings import SoloAPISettings
from route_optimisation.tests.web.mixins import ORToolsMixin
from route_optimisation.tests.web.optimisation_expectation import LogCheck, OptimisationExpectation
from tasks.push_notification.push_messages.order_change_status_composers import BulkAssignedMessage


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class NotificationsAfterOptimisationTestCase(NotificationTestMixin, ORToolsMixin, APITestCase):
    settings = None

    def setUp(self):
        super().setUp()
        settings = SoloAPISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.skill(1, service_time=5)
        settings.skill(2, service_time=0)
        settings.skill(3)
        settings.driver(member_id=1, start_hub=1, end_hub=2, skill_set=(1, 2, 3), end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', skill_set=(1, 2, 3),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', skill_set=(1,),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.service_time(12)
        self.settings = settings

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_push_notifications_about_driver_route(self, push_mock):
        self.settings.set_re_optimise_assigned(True)
        self.settings.set_working_hours(lower=(12,), upper=(19,))
        expected = OptimisationExpectation(skipped_orders=0)
        self.run_optimisation(self.settings, expected)

        bulk_assigned_push_sent, new_route_push_sent = False, False
        bulk_assigned_msg, new_route_msg = [], []
        for (push_composer,), _ in push_mock.call_args_list:
            if isinstance(push_composer, BulkAssignedMessage):
                bulk_assigned_push_sent = True
                bulk_assigned_msg.append(push_composer)
                self.check_push_composer_no_errors(push_composer)
            if isinstance(push_composer, NewRoutePushMessage):
                new_route_push_sent = True
                new_route_msg.append(push_composer)
                self.check_push_composer_no_errors(push_composer)
        self.assertTrue(bulk_assigned_push_sent)
        self.assertTrue(new_route_push_sent)
        self.assertEqual(len(bulk_assigned_msg), 1)
        self.assertEqual(len(new_route_msg), 1)

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_push_notifications_about_individual_driver_route(self, push_mock):
        self.settings.order(3, '-37.8238154,145.0108082', skill_set=(2, 3), driver=1,
                            deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        self.settings.order(4, '-37.755938,145.706767', driver=1,
                            deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        self.settings.set_initiator_driver(1)
        success_expected = OptimisationExpectation(skipped_orders=0)
        success_expected.add_check(LogCheck('2 jobs were included into Optimisation'))
        self.run_solo_optimisation(self.settings, success_expected)

        push_composer_list = [msg[0][0] for msg in push_mock.call_args_list
                              if isinstance(msg[0][0], SoloOptimisationStatusChangeMessage)]
        self.assertEqual(len(push_composer_list), 1)
        push_composer = push_composer_list[0]
        self.assertEqual(push_composer.get_kwargs().get('data', {}).get('status'), 'completed')
        self.check_push_composer_no_errors(push_composer)

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_push_about_individual_driver_route_by_manager(self, push_mock):
        success_expected = OptimisationExpectation(skipped_orders=0)
        self.run_optimisation(self.settings, success_expected)
        push_composer_list = [msg[0][0] for msg in push_mock.call_args_list
                              if isinstance(msg[0][0], NewRoutePushMessage)]
        self.assertEqual(len(push_composer_list), 1)
        self.check_push_composer_no_errors(push_composer_list[0])

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_push_about_failed_individual_optimization(self, push_mock):
        self.settings.driver(member_id=2, start_hub=1, end_hub=2, skill_set=(1, 2, 3), end_time=(18, 0), capacity=15)
        self.settings.set_initiator_driver(1)
        fail_expected = OptimisationExpectation(fail=True)
        self.run_solo_optimisation(self.settings, fail_expected)

        push_composer_list = [msg[0][0] for msg in push_mock.call_args_list
                              if isinstance(msg[0][0], SoloOptimisationStatusChangeMessage)]
        self.assertEqual(len(push_composer_list), 1)
        push_composer = push_composer_list[0]
        self.assertEqual(push_composer.get_kwargs().get('data', {}).get('status'), 'failed')
        self.check_push_composer_no_errors(push_composer)
