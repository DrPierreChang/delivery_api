from django.test import override_settings

from rest_framework.test import APITestCase

from route_optimisation.const import OPTIMISATION_TYPES

from .api_settings import APISettings
from .mixins import ORToolsMixin
from .optimisation_expectation import LogCheck, OptimisationExpectation


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class DistanceMatrixProblemsTestCase(ORToolsMixin, APITestCase):
    def test_skip_not_accessible_orders(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=15)
        settings.order(1, '-37.8421644,144.9399743',
                       deliver_after_time=(9, 0,), deliver_before_time=(19, 0))
        settings.order(2, '53.927430,27.449692',
                       deliver_after_time=(9, 0,), deliver_before_time=(19, 0))
        expectation = OptimisationExpectation(max_distance=40000, skipped_orders=1)
        expectation.add_check(LogCheck('This job is not accessible by geographical reasons', partly=True))
        self.run_optimisation(settings, expectation)

    def test_hubs_on_different_continents(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('53.927430,27.449692', hub_id=2)
        settings.driver(member_id=1, start_hub=1, end_hub=2, capacity=15)
        settings.order(1, '-37.8421644,144.9399743',
                       deliver_after_time=(9, 0,), deliver_before_time=(19, 0))
        expectation = OptimisationExpectation(fail=True)
        expectation.add_check(LogCheck('There are hubs on different continents', partly=True))
        self.run_optimisation(settings, expectation)
