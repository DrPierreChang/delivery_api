import io
from datetime import datetime, time, timedelta

from django.utils import timezone

from PIL import Image

from driver.factories import DriverLocationFactory
from merchant.factories import LabelFactory, SkillSetFactory, SubBrandingFactory

from ...models import Order
from ...models.orders import order_deadline
from ..base_test_cases import BaseOrderTestCase
from ..factories import OrderFactory


class MobileOrderUpdateTestCase(BaseOrderTestCase):
    @classmethod
    def setUpTestData(cls):
        super(MobileOrderUpdateTestCase, cls).setUpTestData()
        cls.merchant.advanced_completion = cls.merchant.ADVANCED_COMPLETION_REQUIRED
        cls.merchant.driver_can_create_job = True
        cls.merchant.use_subbranding = True
        cls.merchant.enable_labels = True
        cls.merchant.option_barcodes = cls.merchant.TYPES_BARCODES.both
        cls.merchant.enable_skill_sets = True
        cls.merchant.use_pick_up_status = True
        cls.merchant.in_app_jobs_assignment = True
        cls.merchant.enable_delivery_pre_confirmation = True
        cls.merchant.enable_delivery_confirmation = True
        cls.merchant.use_way_back_status = True
        cls.merchant.enable_job_description = True
        cls.merchant.save()
        loc = DriverLocationFactory(member=cls.driver)
        cls.driver.last_location = loc
        cls.driver.save()

        cls.skill_sets = SkillSetFactory.create_batch(merchant=cls.merchant, size=3)
        cls.driver.skill_sets.add(cls.skill_sets[0])

        cls.labels = LabelFactory.create_batch(merchant=cls.merchant, size=3)
        cls.sub_branding = SubBrandingFactory(merchant=cls.merchant)

        cls.order = OrderFactory(
            merchant=cls.merchant,
            manager=cls.manager,
            driver=None,
            status=Order.NOT_ASSIGNED,
            deliver_before=order_deadline(),
        )
        cls.job_data = {
            'deliver_address': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357,
                },
            },
            'customer': {
                'name': 'Test20',
            },
        }

    def test_assign_driver(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/mobile/orders/v1/{0}/'.format(self.order.id))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.patch('/api/mobile/orders/v1/{0}/'.format(self.order.id), {
            'status': Order.ASSIGNED,
        })
        self.order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], Order.ASSIGNED)
        self.assertEqual(self.order.status, Order.ASSIGNED)

        resp = self.client.patch('/api/mobile/orders/v1/{0}/'.format(self.order.id), {
            'status': Order.NOT_ASSIGNED,
        })
        self.order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], Order.NOT_ASSIGNED)
        self.assertEqual(self.order.status, Order.NOT_ASSIGNED)

        resp = self.client.patch('/api/mobile/orders/v1/{0}/'.format(self.order.id), {
            'status': Order.ASSIGNED,
        })
        self.order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], Order.ASSIGNED)
        self.assertEqual(self.order.status, Order.ASSIGNED)

    def test_driver_orders(self):
        self.order.driver = self.driver
        self.order.status = 'assigned'
        self.order.save()

        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/mobile/orders/v1/')
        self.assertGreater(resp.data['count'], 0)
        return resp

    def _generate_image(self):
        file = io.BytesIO()
        image = Image.new('RGBA', size=(100, 100), color=(155, 0, 0))
        image.save(file, 'png')
        file.name = 'test.png'
        file.seek(0)
        return file

    def test_workflow_order(self):
        self.merchant.advanced_completion = self.merchant.ADVANCED_COMPLETION_REQUIRED
        self.merchant.driver_can_create_job = True
        self.merchant.use_subbranding = True
        self.merchant.enable_labels = True
        self.merchant.option_barcodes = self.merchant.TYPES_BARCODES.both
        self.merchant.enable_skill_sets = True
        self.merchant.use_pick_up_status = True
        self.merchant.in_app_jobs_assignment = True
        self.merchant.enable_delivery_pre_confirmation = True
        self.merchant.enable_delivery_confirmation = True
        self.merchant.enable_pick_up_confirmation = True
        self.merchant.use_way_back_status = True
        self.merchant.enable_job_description = True
        self.merchant.enable_skids = True
        self.merchant.save()

        self.client.force_authenticate(self.driver)
        path = '/api/mobile/orders/v1/'
        job_data = {
            **self.job_data,
            'skill_set_ids': [self.skill_sets[2].id],
        }
        resp = self.client.post(path, data=job_data)
        self.assertEqual(resp.status_code, 400)

        job_data = {
            **self.job_data,
            'driver_id': self.driver.id,
            'skill_set_ids': [self.skill_sets[1].id],
        }
        resp = self.client.post(path, data=job_data)
        self.assertEqual(resp.status_code, 400)

        tz = self.merchant.timezone
        delivery_date = timezone.now().date() + timedelta(days=1)
        job_data = {
            **self.job_data,
            'driver_id': self.driver.id,
            'label_ids': [self.labels[0].id, self.labels[1].id],
            'skill_set_ids': [self.skill_sets[0].id],
            'sub_branding_id': self.sub_branding.id,
            'barcodes': [{
                'code_data': '123werdfg',
                'requried': True,
            }],
            'title': 'Job: ID 166690399',
            'deliver_before': tz.localize(datetime.combine(delivery_date, time(hour=20))),
            'deliver_after': tz.localize(datetime.combine(delivery_date, time(hour=19))),
            'pickup_before': tz.localize(datetime.combine(delivery_date, time(hour=18))),
            'pickup_after': tz.localize(datetime.combine(delivery_date, time(hour=17))),
            'pickup_address': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357,
                },
            },
            'comment': 'Test comment',
            'pickup': {
                'name': 'Test20',
            },
        }
        resp = self.client.post(path, data=job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['server_entity_id']).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, Order.ASSIGNED)
        self.assertTrue('customer' in resp.data)
        self.assertTrue('description' in resp.data)
        self.assertTrue('pickup_address' in resp.data)
        self.assertTrue('wayback_point' in resp.data)
        self.assertTrue('pick_up_confirmation' in resp.data)
        self.assertTrue('pre_confirmation' in resp.data)
        self.assertTrue('confirmation' in resp.data)
        self.assertTrue('sub_branding' in resp.data)
        self.assertTrue('labels' in resp.data)
        self.assertTrue('skill_sets' in resp.data)
        self.assertTrue('barcodes' in resp.data)
        self.assertTrue('cargoes' in resp.data)

        path = '/api/mobile/orders/v1/{0}/'.format(order.id)

        resp = self.client.patch(path, data={'completion': {'code_ids': [201]}})
        self.assertEqual(resp.status_code, 400)

        resp = self.client.patch(path, data={'status': 'pickup'})
        order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(order.status, Order.PICK_UP)

        resp = self.client.patch(path, data={
            'status': 'in_progress',
            'starting_point': {
                'address': 'Fake address',
                'location': {
                    'lat': 55.5,
                    'lng': 27.5,
                },
            },
        })
        order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(order.status, Order.IN_PROGRESS)

        resp = self.client.patch(path, data={
            'status': 'in_progress',
            'starting_point': None,
        })
        order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)

        image_1 = self._generate_image()
        image_2 = self._generate_image()
        image_3 = self._generate_image()
        image_4 = self._generate_image()
        image_5 = self._generate_image()
        image_6 = self._generate_image()
        resp = self.client.patch(
            path + 'upload_images/',
            data={
                'pre_confirmation_signature': image_1,
                'pre_confirmation_photos': image_2,
                'pre_confirmation_comment': 'Pre comment',
                'confirmation_signature': image_3,
                'confirmation_photos': image_4,
                'confirmation_comment': 'Comment',
                'pick_up_confirmation_signature': image_5,
                'pick_up_confirmation_photos': image_6,
                'pick_up_confirmation_comment': 'Pick up comment',
            },
            format='multipart',
        )
        order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)

        self.assertNotEqual(order.pre_confirmation_signature, None)
        self.assertTrue(order.pre_confirmation_photos.exists())
        self.assertEqual(order.pre_confirmation_comment, 'Pre comment')

        self.assertNotEqual(order.confirmation_signature, None)
        self.assertTrue(order.order_confirmation_photos.exists())
        self.assertEqual(order.confirmation_comment, 'Comment')

        self.assertNotEqual(order.pick_up_confirmation_signature, None)
        self.assertTrue(order.pick_up_confirmation_photos.exists())
        self.assertEqual(order.pick_up_confirmation_comment, 'Pick up comment')

        resp = self.client.patch(path, data={'status': 'way_back'})
        order.refresh_from_db()
        self.assertEqual(resp.status_code, 400)

        resp = self.client.patch(path, data={
            'status': 'way_back',
            'completion': {'code_ids': [201]},
            'wayback_point': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357,
                },
            },
        })
        order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(order.status, Order.WAY_BACK)

        resp = self.client.patch(path, data={'status': 'delivered'})
        order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(order.status, Order.DELIVERED)

        resp = self.client.patch(path, data={
            'ending_point': {
                'address': 'Fake address',
                'location': {
                    'lat': 55.5,
                    'lng': 27.5,
                },
            },
        })
        order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(order.ending_point.address, 'Fake address')

    def test_minimal_workflow_order(self):
        self.merchant.advanced_completion = self.merchant.ADVANCED_COMPLETION_DISABLED
        self.merchant.use_subbranding = False
        self.merchant.enable_labels = False
        self.merchant.option_barcodes = self.merchant.TYPES_BARCODES.disable
        self.merchant.enable_skill_sets = False
        self.merchant.use_pick_up_status = False
        self.merchant.enable_delivery_pre_confirmation = False
        self.merchant.enable_delivery_confirmation = False
        self.merchant.enable_pick_up_confirmation = False
        self.merchant.in_app_jobs_assignment = False
        self.merchant.use_way_back_status = False
        self.merchant.enable_job_description = False
        self.merchant.enable_skids = False
        self.merchant.save()

        self.client.force_authenticate(self.driver)
        path = '/api/mobile/orders/v1/'
        job_data = {
            **self.job_data,
            'driver_id': self.driver.id,
            'label_ids': [self.labels[0].id, self.labels[1].id],
            'skill_set_ids': [self.skill_sets[0].id],
            'sub_branding_id': self.sub_branding.id,
            'barcodes': [{
                'code_data': '123werdfg',
                'requried': True,
            }],
            'title': 'Job: ID 166690399',
            'deliver_before': timezone.now() + timedelta(days=365),
            'deliver_address_2': 'adress',
            'pickup_address': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357,
                },
            },
            'comment': 'Test comment',
        }
        resp = self.client.post(path, data=job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['server_entity_id']).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, Order.ASSIGNED)
        self.assertFalse('description' in resp.data)
        self.assertFalse('pickup_address' in resp.data)
        self.assertFalse('wayback_point' in resp.data)
        self.assertFalse('pre_confirmation' in resp.data)
        self.assertFalse('confirmation' in resp.data)
        self.assertFalse('sub_branding' in resp.data)
        self.assertFalse('labels' in resp.data)
        self.assertFalse('skill_sets' in resp.data)
        self.assertFalse('barcodes' in resp.data)
        self.assertFalse('pickup' in resp.data)
        self.assertFalse('pick_up_confirmation' in resp.data)
        self.assertFalse('cargoes' in resp.data)

        self.merchant.driver_can_create_job = False
        self.merchant.save()

        path = '/api/mobile/orders/v1/{0}/'.format(order.id)

        resp = self.client.patch(path, data={'status': 'in_progress'})
        order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(order.status, Order.IN_PROGRESS)

        resp = self.client.patch(path, data={'status': 'delivered'})
        order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(order.status, Order.DELIVERED)

    def test_mobile_orders_path_getting(self):
        self.order.status = Order.ASSIGNED
        self.order.driver = self.driver
        locations = list(DriverLocationFactory.create_batch(size=10, member=self.driver))
        self.order.path = {'way_back': [f'{loc.location}{count}' for count, loc in enumerate(locations)]}
        self.order.save()

        self.client.force_authenticate(self.driver)
        resp = self.client.get(f'/api/mobile/orders/v1/{self.order.id}/path/')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['path']['way_back']), len(locations))

    def test_mobile_empty_orders_path_getting(self):
        self.order.status = Order.ASSIGNED
        self.order.driver = self.driver
        self.order.path = {}
        self.order.save()

        self.client.force_authenticate(self.driver)
        resp = self.client.get(f'/api/mobile/orders/v1/{self.order.id}/path/')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['path'], None)
