from datetime import datetime, time, timedelta

from django.utils import timezone

from driver.factories import DriverLocationFactory
from merchant.factories import LabelFactory, SkillSetFactory, SubBrandingFactory

from ...models import Order
from ..base_test_cases import BaseOrderTestCase


class MobileOrderTestCase(BaseOrderTestCase):
    @classmethod
    def setUpTestData(cls):
        super(MobileOrderTestCase, cls).setUpTestData()
        cls.merchant.driver_can_create_job = True
        cls.merchant.use_subbranding = True
        cls.merchant.enable_labels = True
        cls.merchant.enable_skill_sets = True
        cls.merchant.option_barcodes = cls.merchant.TYPES_BARCODES.both
        cls.merchant.use_pick_up_status = True
        cls.merchant.save()
        loc = DriverLocationFactory(member=cls.driver)
        cls.driver.last_location = loc
        cls.driver.save()
        cls.job_data = {
            'deliver_address': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357,
                }
            },
            'customer': {
                'name': 'Test20',
            },
        }
        cls.labels = LabelFactory.create_batch(merchant=cls.merchant, size=3)

        cls.skill_sets = SkillSetFactory.create_batch(merchant=cls.merchant, size=3)
        cls.driver.skill_sets.add(cls.skill_sets[0])

        cls.secret_skill_sets = SkillSetFactory.create_batch(merchant=cls.merchant, is_secret=True, size=3)
        cls.driver.skill_sets.add(cls.secret_skill_sets[0])

        cls.sub_branding = SubBrandingFactory(merchant=cls.merchant)

    def test_create_order(self):
        self.client.force_authenticate(self.driver)
        self.merchant.driver_can_create_job = False
        self.merchant.save()

        resp = self.client.post('/api/mobile/orders/v1/', data=self.job_data)
        self.assertEqual(resp.status_code, 403)

        self.merchant.driver_can_create_job = True
        self.merchant.save()

        resp = self.client.post('/api/mobile/orders/v1/', data=self.job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['server_entity_id']).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, Order.NOT_ASSIGNED)

    def test_create_order_with_labels(self):
        self.client.force_authenticate(self.driver)
        job_data = {
            'label_ids': [self.labels[0].id, self.labels[1].id],
            **self.job_data,
        }

        resp = self.client.post('/api/mobile/orders/v1/', data=job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['server_entity_id']).first()
        self.assertIsNotNone(order)
        self.assertEqual(len(resp.data['labels']), 2)
        self.assertEqual(order.status, Order.NOT_ASSIGNED)

    def test_create_order_with_skill_sets(self):
        self.client.force_authenticate(self.driver)
        job_data = {
            'skill_set_ids': [self.skill_sets[0].id, self.secret_skill_sets[0].id],
            **self.job_data,
        }

        resp = self.client.post('/api/mobile/orders/v1/', data=job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['server_entity_id']).first()
        self.assertIsNotNone(order)
        self.assertEqual(len(resp.data['skill_sets']), 2)
        self.assertEqual(order.status, Order.NOT_ASSIGNED)

    def test_create_order_with_sub_branding(self):
        self.client.force_authenticate(self.driver)
        job_data = {
            'sub_branding_id': self.sub_branding.id,
            **self.job_data,
        }

        resp = self.client.post('/api/mobile/orders/v1/', data=job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['server_entity_id']).first()
        self.assertIsNotNone(order)
        self.assertEqual(resp.data['sub_branding']['id'], self.sub_branding.id)
        self.assertEqual(order.status, Order.NOT_ASSIGNED)

    def test_create_order_with_barcodes(self):
        self.client.force_authenticate(self.driver)
        job_data = {
            'barcodes': [{
                'code_data': '123werdfg',
                'requried': True
            }],
            **self.job_data,
        }

        resp = self.client.post('/api/mobile/orders/v1/', data=job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['server_entity_id']).first()
        self.assertIsNotNone(order)
        self.assertEqual(len(resp.data['barcodes']), 1)
        self.assertEqual(order.status, Order.NOT_ASSIGNED)

    def test_create_order_with_driver(self):
        self.client.force_authenticate(self.driver)
        job_data = {
            'driver_id': self.driver.id,
            **self.job_data,
        }

        resp = self.client.post('/api/mobile/orders/v1/', data=job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['server_entity_id'], driver=self.driver).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, Order.ASSIGNED)

    def test_create_order_with_driver_and_skill_sets(self):
        self.client.force_authenticate(self.driver)
        job_data = {
            'driver_id': self.driver.id,
            'skill_set_ids': [self.skill_sets[0].id],
            **self.job_data,
        }

        resp = self.client.post('/api/mobile/orders/v1/', data=job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['server_entity_id'], driver=self.driver).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, Order.ASSIGNED)

    def test_validation_create_order_with_driver_and_skill_sets(self):
        self.client.force_authenticate(self.driver)
        job_data = {
            'driver_id': self.driver.id,
            'skill_set_ids': [self.skill_sets[2].id],
            **self.job_data,
        }

        resp = self.client.post('/api/mobile/orders/v1/', data=job_data)
        self.assertEqual(resp.status_code, 400)

    def test_create_order_with_everything(self):
        self.client.force_authenticate(self.driver)
        tz = self.merchant.timezone
        delivery_date = timezone.now().date() + timedelta(days=1)
        job_data = {
            'driver_id': self.driver.id,
            'label_ids': [self.labels[0].id, self.labels[1].id],
            'skill_set_ids': [self.skill_sets[0].id],
            'sub_branding_id': self.sub_branding.id,
            'barcodes': [{
                'code_data': '123werdfg',
                'requried': True
            }],
            'deliver_address': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357,
                },
                'secondary_address': '6'
            },
            'customer': {
                'name': 'Test20',
            },
            'pickup': {
                'name': 'Test21',
            },
            'title': 'Job: ID 166690399',
            'deliver_before': tz.localize(datetime.combine(delivery_date, time(hour=20))),
            'deliver_after': tz.localize(datetime.combine(delivery_date, time(hour=19))),
            'pickup_before': tz.localize(datetime.combine(delivery_date, time(hour=18))),
            'pickup_after': tz.localize(datetime.combine(delivery_date, time(hour=17))),
            'pickup_address': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357
                }
            },
            'comment': 'Test comment',
        }

        resp = self.client.post('/api/mobile/orders/v1/', data=job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['server_entity_id'], driver=self.driver).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, Order.ASSIGNED)

    def test_getting_terminate_codes(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/mobile/completion_codes/v1/')
        self.assertEqual(resp.status_code, 200)
