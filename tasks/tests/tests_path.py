from itertools import chain

from rest_framework.test import APITestCase

import factory

from base.factories import DriverFactory
from base.utils import get_fuzzy_location
from driver.factories import DriverLocationFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from tasks.models import Order
from tasks.tests.factories import OrderFactory


class OrderPathTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(use_pick_up_status=True)

    def setUp(self):
        self.driver = DriverFactory(merchant=self.merchant, work_status=WorkStatus.WORKING)
        self.order = OrderFactory(merchant=self.merchant, status=Order.ASSIGNED, driver=self.driver)

    def test_picked_up_path(self):
        order_url = '/api/orders/{}'.format(self.order.order_id)
        self.client.force_authenticate(self.driver)
        self.client.put(order_url + '/status', data={'status': Order.PICK_UP})
        DriverLocationFactory.create_batch(size=4,
                                           location=factory.LazyFunction(get_fuzzy_location),
                                           member=self.driver)
        self.client.put(order_url + '/status', data={'status': Order.PICKED_UP})
        picked_up_location = DriverLocationFactory.create(location=factory.LazyFunction(get_fuzzy_location),
                                                          member=self.driver)
        self.client.put(order_url + '/status', data={'status': Order.IN_PROGRESS})
        DriverLocationFactory.create_batch(size=4,
                                           location=factory.LazyFunction(get_fuzzy_location),
                                           member=self.driver)
        self.client.put(order_url + '/status', data={'status': Order.DELIVERED})
        full_path = list(chain.from_iterable(Order.objects.get(id=self.order.id).real_path.values()))
        self.assertTrue(picked_up_location.location not in full_path)

    def test_order_real_path_partition(self):
        self.merchant.use_way_back_status = True
        self.merchant.save()
        order_url = '/api/orders/{}'.format(self.order.order_id)
        self.client.force_authenticate(self.driver)
        self.client.put(order_url + '/status', data={'status': Order.PICK_UP})
        pickup_loc = DriverLocationFactory.create(location=factory.LazyFunction(get_fuzzy_location),
                                                  member=self.driver)
        self.client.put(order_url + '/status', data={'status': Order.PICKED_UP})
        picked_up_loc = DriverLocationFactory.create(location=factory.LazyFunction(get_fuzzy_location),
                                                     member=self.driver)
        self.client.put(order_url + '/status', data={'status': Order.IN_PROGRESS})
        in_progress_loc = DriverLocationFactory.create(location=factory.LazyFunction(get_fuzzy_location),
                                                       member=self.driver)
        self.client.put(order_url + '/status', data={'status': Order.WAY_BACK})
        wayback_loc = DriverLocationFactory.create(location=factory.LazyFunction(get_fuzzy_location),
                                                   member=self.driver)
        self.client.put(order_url + '/status', data={'status': Order.DELIVERED})

        expected_path_data = {
            'pickup': [pickup_loc.location],
            'in_progress': [in_progress_loc.location],
            'way_back': [wayback_loc.location]
        }
        self.assertEqual(Order.objects.get(id=self.order.id).real_path, expected_path_data)
