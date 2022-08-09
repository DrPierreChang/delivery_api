from __future__ import absolute_import, unicode_literals

from rest_framework.fields import empty

import factory

from base.factories import DriverFactory, SubManagerFactory
from driver.tests.base_test_cases import BaseDriverTestCase
from merchant.factories import SubBrandingFactory
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.tests.factories import CustomerFactory, OrderFactory


class BaseOrderTestCase(BaseDriverTestCase):
    @classmethod
    def setUpTestData(cls):
        super(BaseOrderTestCase, cls).setUpTestData()
        cls.customer = CustomerFactory(merchant=cls.merchant)
        cls.sub_branding = SubBrandingFactory(merchant=cls.merchant)
        cls.submanager = SubManagerFactory(merchant=cls.merchant, sub_branding=cls.sub_branding)

    @staticmethod
    def create_order(manager, merchant, customer, driver=empty, **kwargs):
        if driver is empty:
            driver = DriverFactory(merchant=merchant)
        return OrderFactory(manager=manager, merchant=merchant, customer=customer, driver=driver,**kwargs)

    def create_default_order(self, **kwargs):
        return self.create_order(self.manager, self.merchant, self.customer, **kwargs)

    def create_default_order_with_status(self, status=OrderStatus.ASSIGNED, **kwargs):
        order = self.create_default_order(driver=self.driver, status=status, **kwargs)
        return order

    @staticmethod
    def order_batch_without_save(**kwargs):
        return factory.build_batch(Order, FACTORY_CLASS=OrderFactory, **kwargs)

    def default_order_batch(self, **kwargs):
        return OrderFactory.create_batch(
            merchant=self.merchant,
            manager=self.manager,
            driver=self.driver,
            customer=self.customer,
            **kwargs
        )
