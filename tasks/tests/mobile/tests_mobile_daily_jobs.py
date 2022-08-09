from datetime import timedelta

from django.utils import timezone

from rest_framework.test import APITestCase

from notification.tests.mixins import NotificationTestMixin
from route_optimisation.const import OPTIMISATION_TYPES
from route_optimisation.tests.web.api_settings import APISettings
from route_optimisation.tests.web.mixins import ORToolsMixin
from route_optimisation.tests.web.optimisation_expectation import OptimisationExpectation


class RemoveRouteOptimisationAPITestCase(NotificationTestMixin, ORToolsMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.manager)
        self.settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                                    self.merchant, self.manager)
        self.settings.hub('-37.869197,144.820283', hub_id=1)
        self.settings.hub('-37.868197,144.820183', hub_id=2)
        self.settings.driver(member_id=1, start_hub=1, end_hub=2, capacity=15)
        self.driver = self.settings.drivers_map[1]
        self.settings.order(1, '-37.6780953, 145.1290807')
        self.settings.order(2, '-37.926451, 144.998992')
        self.settings.order(3, '-35.5418094, 144.9643013')
        self.settings.order(4, '-37.9202176, 145.2230781')
        self.expectation = OptimisationExpectation(skipped_orders=0)

    def test_get_daily_jobs(self):
        opt_id = self.run_optimisation(self.settings, self.expectation)

        self.client.force_authenticate(self.driver)

        date_from = (timezone.now() - timedelta(days=5)).date()
        date_to = (timezone.now() + timedelta(days=5)).date()
        resp = self.client.get('/api/mobile/daily_orders/v1/', data={'date_from': date_from, 'date_to': date_to})
        self.assertEqual(resp.status_code, 200)
